"""The Memory Engine (Final Build Plan §13.1 / New Plan §12.7).

``MemoryEngine`` is the §13.1 *Memory Manager* — the seven verbs::

    remember · retrieve · search · update · forget · summarize · link

— assembled over the §12.4 SQLite index, the §12.5 vector layer and
the §12.8 resolver. It is the default :class:`MemoryProvider`.

The §12.7 retrieval pipeline, verbatim, one method per arrow::

    Prompt ───────────► MemoryQuery           (_query_from)
    Task / Workspace ─► container context      (same)
    ─────────────────► Relevant Memory Search  (_search_candidates)
                        vector stage + lexical stage + provenance
    ─────────────────► Ranking                 (_rank)
                        0.45 semantic + 0.20 lexical + 0.15 recency
                        + 0.10 confidence + 0.10 scope-fit
    ─────────────────► Conflict Resolution     (_resolve)
                        the §12.8 ladder
    ─────────────────► Context                 (_assemble)
                        budget-capped blocks, honest drop counts

Ranking weights are module constants — documented, deterministic,
unit-tested (``RANK_WEIGHTS``). Recency uses a 14-day half-life so an
evening-old fact out-ranks last month's. Scope-fit rewards the ladder:
a TASK memory beats a GLOBAL one at equal relevance because it is
*closer to the question*.

Events: MEMORY_CREATED / MEMORY_UPDATED ride the §2.2 bus when one is
attached (forget stays audit-only — §2.2 has no forgotten event, and
the §12.4 audit table is the legal record).

محرّك الذاكرة — سبعة أفعال وخط استرجاع بخمس مراحل موزونة
وحتمية؛ السياق النهائي مقيّد بالميزانية وصادق بعدد المسقطات.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .compression import (
    COMPRESS_CHAR_THRESHOLD,
    COMPRESS_TURN_THRESHOLD,
    COMPRESSION_STAGES,
    MemoryCompressor,
    should_compress,
)
from .conflict import ConflictOutcome, ConflictResolver, _parse_ts
from .contracts import (
    ForgetResult,
    InvalidMemoryError,
    MemoryEvidence,
    MemoryNotFoundError,
    MemoryProvider,
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemorySearchHit,
    MemoryType,
    new_memory_id,
    scope_visible,
)
from .embeddings import EmbeddingProvider, HashingEmbedder, tokenize
from .forget import ForgetOps
from .store import SQLiteMemoryStore
from .vectors import (
    LocalVectorIndex,
    VectorIndex,
    record_payload,
    resolve_vector_index,
)

#: §12.7 relevance floor — a candidate must actually match the query:
#: lexical overlap > 0, or a *strong* semantic score. Weak vector
#: scores (hash collisions / unrelated paraphrases at real embedders)
#: plus the base rank terms would otherwise flood the context with
#: fresh-but-irrelevant memories — the exit-gate E section caught
#: exactly that ("لا تسترجع كل الذاكرة" — Plan §13.6).
SEMANTIC_STRONG = 0.55

#: §12.7 ranking weights — documented, deterministic, tested.
RANK_WEIGHTS: dict[str, float] = {
    "semantic": 0.45,
    "lexical": 0.20,
    "recency": 0.15,
    "confidence": 0.10,
    "scope_fit": 0.10,
}

#: Recency half-life (days) — an evening-old fact beats last month's.
RECENCY_HALF_LIFE_DAYS = 14.0

#: Scope-fit scores — the §12.2 ladder as a number.
SCOPE_FIT: dict[str, float] = {
    MemoryScope.TASK: 1.0,
    MemoryScope.SESSION: 0.95,
    MemoryScope.WORKSPACE: 0.8,
    MemoryScope.PROJECT: 0.6,
    MemoryScope.USER: 0.4,
    MemoryScope.GLOBAL: 0.3,
    MemoryScope.AGENT: 0.5,
    MemoryScope.KNOWLEDGE: 0.35,
    MemoryScope.DECISION: 0.45,
    MemoryScope.LESSON: 0.3,
    MemoryScope.SKILL: 0.35,
    MemoryScope.ERROR: 0.3,
}

#: Context block order (§12.7 assemble stage).
BLOCK_ORDER: tuple[str, ...] = (
    "rules",
    "preferences",
    "decisions",
    "lessons",
    "facts",
    "knowledge",
    "events",
    "summary",
)


def _recency_score(updated_at: str, now: datetime) -> float:
    """exp(-ln2 · age_days / half_life) — 1.0 now, 0.5 a fortnight later."""
    stamp = _parse_ts(updated_at)
    if stamp == datetime.min.replace(tzinfo=UTC):
        return 0.0
    age_days = max((now - stamp).total_seconds(), 0.0) / 86_400.0
    import math

    return math.exp(-math.log(2.0) * age_days / RECENCY_HALF_LIFE_DAYS)


def rank_score(
    record: MemoryRecord,
    *,
    semantic: float,
    lexical: float,
    now: datetime,
) -> float:
    """The §12.7 ranking formula — pure, deterministic, unit-tested."""
    return (
        RANK_WEIGHTS["semantic"] * max(semantic, 0.0)
        + RANK_WEIGHTS["lexical"] * lexical
        + RANK_WEIGHTS["recency"] * _recency_score(record.updated_at, now)
        + RANK_WEIGHTS["confidence"] * record.confidence
        + RANK_WEIGHTS["scope_fit"] * SCOPE_FIT.get(record.scope, 0.3)
    )


def _block_kind(record: MemoryRecord) -> str:
    """Map a record onto its context block (§12.7 assemble)."""
    mapping = {
        MemoryType.RULE: "rules",
        MemoryType.PREFERENCE: "preferences",
        MemoryType.DECISION: "decisions",
        MemoryType.LESSON: "lessons",
        MemoryType.FACT: "facts",
        MemoryType.KNOWLEDGE: "knowledge",
        MemoryType.OBSERVATION: "facts",
        MemoryType.EVENT: "events",
        MemoryType.SUMMARY: "summary",
        MemoryType.NOTE: "facts",
        MemoryType.SKILL: "knowledge",
        MemoryType.ERROR: "lessons",
    }
    return mapping.get(record.type, "facts")


@dataclass(slots=True)
class ContextBlock:
    """One assembled context block — kind, text, source record."""

    kind: str
    text: str
    record_id: str


@dataclass(slots=True)
class MemoryContext:
    """The §12.7 output — what the harness renders into §41 context."""

    prompt: str = ""
    blocks: list[ContextBlock] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    dropped: int = 0
    budget_chars: int = 6000
    provenance: tuple[str, ...] = ()

    @property
    def total_chars(self) -> int:
        return sum(len(block.text) for block in self.blocks)

    def as_prompt(self) -> str:
        """Render the blocks as one context string (§41 memory view)."""
        if not self.blocks:
            return ""
        grouped: dict[str, list[str]] = {}
        for block in self.blocks:
            grouped.setdefault(block.kind, []).append(block.text)
        parts: list[str] = []
        for kind in BLOCK_ORDER:
            if kind in grouped:
                lines = "\n".join(f"- {text}" for text in grouped[kind])
                parts.append(f"[{kind}]\n{lines}")
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "blocks": [
                {"kind": block.kind, "text": block.text, "record": block.record_id}
                for block in self.blocks
            ],
            "conflicts": list(self.conflicts),
            "dropped": self.dropped,
            "budget_chars": self.budget_chars,
            "provenance": list(self.provenance),
            "total_chars": self.total_chars,
        }


class MemoryEngine(MemoryProvider):
    """The default provider — §13.1 verbs over §12.4 + §12.5 + §12.8.

    ``store``        — SQLiteMemoryStore (path or ``:memory:``).
    ``embedder``     — any EmbeddingProvider (default: HashingEmbedder).
    ``vector_index`` — any VectorIndex (default: LocalVectorIndex over
                       the same store; Qdrant via the factory).
    ``bus``          — optional §2.2 EventBus for MEMORY_* events.
    """

    def __init__(
        self,
        store: SQLiteMemoryStore,
        *,
        embedder: EmbeddingProvider | None = None,
        vector_index: VectorIndex | None = None,
        bus: object | None = None,
        backend_report: str = "LocalVectorIndex (explicit constructor)",
    ) -> None:
        self._store = store
        self._embedder = embedder or HashingEmbedder()
        self._vectors = vector_index or LocalVectorIndex(store)
        self._resolver = ConflictResolver()
        self._compressor = MemoryCompressor()
        self._forget = ForgetOps(store)
        self._bus = bus
        self.backend_report = backend_report

    # ------------------------------------------------------------ remember

    def remember(
        self,
        content: str,
        *,
        type: str = MemoryType.FACT,  # noqa: A002 — §13.1 verb name
        scope: str = MemoryScope.GLOBAL,
        source: str = "system",
        confidence: float = 1.0,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
        conflict_key: str | None = None,
        expires_at: str | None = None,
        evidence: tuple[MemoryEvidence, ...] = (),
    ) -> MemoryRecord:
        """Write one memory — store + vector, atomically visible."""
        for ev in evidence:
            ev.validate()
        record = MemoryRecord(
            id=new_memory_id(),
            type=type,
            scope=scope,
            content=content,
            source=source,
            confidence=confidence,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
            agent=agent,
            conflict_key=conflict_key,
            expires_at=expires_at,
            evidence=evidence,
        )
        self._store.add_record(record)
        self._vectors.upsert(
            [(record.id, self._embedder.embed(record.content), record_payload(record))]
        )
        self._emit("memory.created", record)
        return record

    # ------------------------------------------------------------- search

    def search(self, query: MemoryQuery) -> list[MemorySearchHit]:
        """Ranked search — the §12.7 pipeline minus context assembly."""
        now = datetime.now(UTC)
        candidates = self._search_candidates(query, now)
        ranked = self._rank(candidates, now)
        return ranked[: query.limit]

    # ----------------------------------------------------------- retrieve

    def retrieve(
        self,
        prompt: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
        limit: int = 16,
        budget_chars: int = 6000,
    ) -> MemoryContext:
        """The full §12.7 pipeline → a budget-capped MemoryContext."""
        query = MemoryQuery(
            text=prompt,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
            agent=agent,
            limit=limit,
        )
        now = datetime.now(UTC)
        candidates = self._search_candidates(query, now)
        ranked = self._rank(candidates, now)[: query.limit]
        kept, notes = self._resolve(ranked)
        context = self._assemble(query, kept, notes, budget_chars)
        return context

    # ------------------------------------------------------------- update

    def update(
        self,
        record_id: str,
        *,
        content: str | None = None,
        confidence: float | None = None,
        expires_at: str | None = None,
    ) -> MemoryRecord:
        """Update a memory — content/confidence/expiry + re-embed."""
        record = self._store.update_record(
            record_id,
            content=content,
            confidence=confidence,
            expires_at=expires_at,
        )
        self._vectors.delete([record_id])
        self._vectors.upsert(
            [(record.id, self._embedder.embed(record.content), record_payload(record))]
        )
        self._emit("memory.updated", record)
        return record

    # -------------------------------------------------------------- forget

    def forget(
        self,
        *,
        record_id: str | None = None,
        type: str | None = None,  # noqa: A002 — §12.9 category
        scope: str | None = None,  # noqa: A002 — §12.9 scope
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
        reason: str = "operator request",
        requested_by: str = "operator",
        allow_global: bool = False,
    ) -> ForgetResult:
        """§12.9 — exact / category / scope, always audited."""
        if record_id is not None:
            self._vectors.delete([record_id])
            return self._forget.forget_exact(
                record_id, reason=reason, requested_by=requested_by
            )
        if type is not None:
            result = self._forget.forget_category(
                type,
                project=project,
                workspace=workspace,
                task=task,
                reason=reason,
                requested_by=requested_by,
            )
            self._vectors.delete(result.forgotten)
            return result
        if scope is not None:
            result = self._forget.forget_scope(
                scope,
                project=project,
                workspace=workspace,
                task=task,
                session=session,
                agent=agent,
                reason=reason,
                requested_by=requested_by,
                allow_global=allow_global,
            )
            self._vectors.delete(result.forgotten)
            return result
        raise InvalidMemoryError(
            "forget needs one of: record_id= (exact) or type= (category) "
            "or scope= (scope) — §12.9's three verbs"
        )

    # ----------------------------------------------------------- summarize

    def summarize(
        self,
        *,
        record_ids: tuple[str, ...] = (),
        turns: tuple[dict[str, Any], ...] = (),
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
    ) -> MemoryRecord:
        """§12.10 compression — over raw turns or over stored records.

        Both paths mint one compact SUMMARY record, write the extracted
        records, and link everything with ``compressed_from``.
        """
        if turns:
            extracted, summary = self._compressor.summarize(
                [dict(turn) for turn in turns],
                session=session,
                task=task,
                project=project,
                workspace=workspace,
            )
        elif record_ids:
            records = [self._store.get_record(rid) for rid in record_ids]
            pseudo_turns: list[dict[str, Any]] = [
                {
                    "role": "memory",
                    "content": record.content,
                    "kind": "artifact",
                    "at": record.updated_at,
                }
                for record in records
            ]
            extracted, summary = self._compressor.summarize(
                pseudo_turns,
                session=session,
                task=task,
                project=project,
                workspace=workspace,
            )
        else:
            raise InvalidMemoryError(
                "summarize needs turns= (raw history) or record_ids= (stored)"
            )
        # the compressor already scoped and stamped the containers; the
        # engine only persists, embeds, links
        # persist: extracted first, then the summary, then the links
        for item in extracted:
            self._store.add_record(item.record)
            self._vectors.upsert(
                [
                    (
                        item.record.id,
                        self._embedder.embed(item.record.content),
                        record_payload(item.record),
                    )
                ]
            )
            self._emit("memory.created", item.record)
        self._store.add_record(summary)
        self._vectors.upsert(
            [(summary.id, self._embedder.embed(summary.content), record_payload(summary))]
        )
        self._emit("memory.created", summary)
        for item in extracted:
            self.link(summary.id, item.record.id, "compressed_from")
        return summary

    # ---------------------------------------------------------------- link

    def link(
        self,
        record_id: str,
        related_id: str,
        relation: str = "links",
    ) -> None:
        """§13.1 link — one edge in the §12.4 relationship graph."""
        self._store.get_record(record_id)  # both must exist (404 fast)
        self._store.get_record(related_id)
        self._store.add_relationship(record_id, related_id, relation)

    # ----------------------------------------------------------- pipeline

    def _query_from(self, prompt: str, **containers: Any) -> MemoryQuery:  # noqa: ARG002
        """§12.7 stage 1 — Prompt → MemoryQuery."""
        return MemoryQuery(text=prompt, **containers)

    def _search_candidates(
        self, query: MemoryQuery, now: datetime
    ) -> list[MemorySearchHit]:
        """§12.7 stage 3 — Relevant Memory Search (vector + lexical).

        Merge semantics: a record found by both stages keeps both
        scores; visibility (§12.2) and freshness are applied *before*
        merging so neither stage can leak an invisible record.
        """
        # expiry sweep first — expired memories never compete
        self._store.sweep_expired(now.isoformat())
        by_id: dict[str, MemorySearchHit] = {}
        needle_text = query.text.strip()
        if needle_text and query.include_semantic:
            vector = self._embedder.embed(needle_text)
            flt: dict[str, Any] = {}
            if query.scope:
                flt["scope"] = query.scope
            for hit in self._vectors.search(
                vector, limit=query.vector_top_k, flt=flt or None
            ):
                try:
                    record = self._store.get_record(hit.record_id)
                except MemoryNotFoundError:
                    continue  # tombstoned after the vector was written
                if not record.active:
                    continue
                # §12.2 scope isolation applies to EVERY stage — the
                # vector engine cannot leak a container it never saw
                if not scope_visible(record, query):
                    continue
                if not _time_window(record, query):
                    continue
                if query.types and record.type not in query.types:
                    continue
                if record.confidence < query.min_confidence:
                    continue
                found = by_id.get(
                    hit.record_id,
                    MemorySearchHit(record=record, score=0.0, provenance=()),
                )
                found.semantic = max(found.semantic, hit.score)
                found.provenance = found.provenance + ("vector",)
                by_id[hit.record_id] = found
        if needle_text:
            needles = [token for token in tokenize(needle_text) if len(token) > 1]
            for record in self._store.lexical_search(needles, limit=64):
                if not scope_visible(record, query):
                    continue
                if not _time_window(record, query):
                    continue
                if query.scope and record.scope != query.scope:
                    continue
                if query.types and record.type not in query.types:
                    continue
                if record.confidence < query.min_confidence:
                    continue
                hay = record.content.casefold()
                hits = sum(1 for token in needles if token in hay)
                lexical = min(hits / max(len(needles), 1), 1.0)
                found = by_id.get(
                    record.id,
                    MemorySearchHit(record=record, score=0.0, provenance=()),
                )
                found.lexical = max(found.lexical, lexical)
                found.provenance = found.provenance + ("lexical",)
                by_id[record.id] = found
            # §12.7/§12.8: operator-authored behavioral RULES in the
            # GLOBAL/USER scopes ride every context — the conflict
            # ladder expects them present ("Workspace rules" is a
            # ladder level). They are few, operator-curated, and the
            # whole point of writing one is that the agent always
            # sees it.
            for record in self._store.iter_records(active_only=True):
                if record.type != MemoryType.RULE:
                    continue
                if record.scope not in (MemoryScope.GLOBAL, MemoryScope.USER):
                    continue
                if record.id in by_id:
                    continue
                if not scope_visible(record, query):
                    continue
                by_id[record.id] = MemorySearchHit(
                    record=record, score=0.0, provenance=("rule",)
                )
        # §12.7 relevance floor — only genuine matches compete (the
        # always-on rules above are the documented exemption)
        relevant = [
            hit
            for hit in by_id.values()
            if "rule" in hit.provenance
            or hit.lexical > 0.0
            or hit.semantic >= SEMANTIC_STRONG
        ]
        return [hit for hit in relevant if _final_filters(hit, query)]

    def _rank(self, candidates: list[MemorySearchHit], now: datetime) -> list[MemorySearchHit]:
        """§12.7 stage 4 — Ranking (documented weights)."""
        for hit in candidates:
            hit.score = rank_score(
                hit.record,
                semantic=hit.semantic,
                lexical=hit.lexical,
                now=now,
            )
        candidates.sort(key=lambda hit: (-hit.score, hit.record.id))
        return candidates

    def _resolve(
        self, ranked: list[MemorySearchHit]
    ) -> tuple[list[MemorySearchHit], list[ConflictOutcome]]:
        """§12.7 stage 5 — Conflict Resolution (§12.8 ladder)."""
        records = [hit.record for hit in ranked]
        kept, notes = self._resolver.resolve(records)
        keep_ids = {record.id for record in kept}
        kept_hits = [hit for hit in ranked if hit.record.id in keep_ids]
        return kept_hits, notes

    def _assemble(
        self,
        query: MemoryQuery,
        hits: list[MemorySearchHit],
        notes: list[ConflictOutcome],
        budget_chars: int,
    ) -> MemoryContext:
        """§12.7 stage 6 — Context assembly under a char budget."""
        context = MemoryContext(
            prompt=query.text,
            budget_chars=budget_chars,
            provenance=tuple(
                sorted({p for hit in hits for p in hit.provenance})
            ),
        )
        used = 0
        dropped = 0
        for hit in hits:
            record = hit.record
            text = f"{record.content} (source: {record.source}, conf: {record.confidence:.2f})"
            if used + len(text) > budget_chars:
                dropped += 1
                continue
            used += len(text)
            context.blocks.append(
                ContextBlock(kind=_block_kind(record), text=text, record_id=record.id)
            )
        context.dropped = dropped
        context.conflicts = [note.describe() for note in notes]
        return context

    # ------------------------------------------------------------ plumbing

    def close(self) -> None:
        """Release every backend resource (Qdrant's local-mode storage
        lock, the SQLite handle) — restart tests depend on this."""
        closer = getattr(self._vectors, "close", None)
        if callable(closer):
            closer()
        self._store.close()

    def _emit(self, name: str, record: MemoryRecord) -> None:
        if self._bus is None:
            return
        try:
            self._bus.publish(name, payload=record.to_dict())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — the bus must never break memory
            pass

    # -------------------------------------------------- introspection/ops

    def backend(self) -> dict[str, Any]:
        """Honest capability report (factory decision + counts)."""
        return {
            "vector_backend": self._vectors.name,
            "embedder": self._embedder.name,
            "dimension": self._embedder.dimension,
            "report": self.backend_report,
            "records": self._store.count_records(),
            "vectors": self._vectors.count(),
            "relationships": self._store.count_relationships(),
        }

    def audit_log(self, *, limit: int = 100):
        """§12.9 audit rows (delegated to the store)."""
        return self._store.audit_log(limit=limit)

    def sweep_expired(self) -> list[str]:
        """Expire memories past their expires_at (§12.3)."""
        return self._store.sweep_expired()

    def compression_state(
        self, turns: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """§12.10 trigger state — honest numbers for the caller."""
        chars = sum(len(str(turn.get("content", ""))) for turn in turns)
        return {
            "turns": len(turns),
            "chars": chars,
            "turn_threshold": COMPRESS_TURN_THRESHOLD,
            "char_threshold": COMPRESS_CHAR_THRESHOLD,
            "should_compress": should_compress(turns, chars),
            "stages": list(COMPRESSION_STAGES),
        }


def _time_window(record: MemoryRecord, query: MemoryQuery) -> bool:
    if query.since and record.updated_at < query.since:
        return False
    if query.until and record.updated_at > query.until:
        return False
    return True


def _final_filters(hit: MemorySearchHit, query: MemoryQuery) -> bool:
    record = hit.record
    if query.scope and record.scope != query.scope:
        return False
    if query.types and record.type not in query.types:
        return False
    if record.confidence < query.min_confidence:
        return False
    return True


# ------------------------------------------------------------- §12.5 note

#: The twelve §12.2 scopes and eleven §12.3 fields are re-exported from
#: contracts for callers who import from the engine module.


# ----------------------------------------------------------------- factory


def build_memory_engine(
    root: str | Path | None = None,
    *,
    embedder: EmbeddingProvider | None = None,
    vector_backend: str = "auto",
    qdrant_location: str | None = None,
    bus: object | None = None,
    store: SQLiteMemoryStore | None = None,
) -> MemoryEngine:
    """Assemble the default engine — honest backend report included.

    ``root``             — data root; the index lands at
                           ``<root>/memory/memory.db`` (``:memory:``
                           when None — tests).
    ``vector_backend``   — ``auto`` (qdrant when installed, local else),
                           ``local``, or ``qdrant`` (hard requirement).
    ``qdrant_location``  — ``:memory:`` (default) / path / URL for the
                           §12.5 adapter. A *path* location persists
                           locally without any server.
    """
    if store is None:
        path = ":memory:" if root is None else str(Path(root) / "memory" / "memory.db")
        store = SQLiteMemoryStore(path)
    chosen_embedder = embedder or HashingEmbedder()
    if vector_backend == "auto" and qdrant_location is None:
        # auto prefers qdrant's persisted local mode under the data root
        if root is not None:
            qdrant_location = str(Path(root) / "memory" / "qdrant")
        else:
            qdrant_location = ":memory:"
    index, report = resolve_vector_index(
        store,
        backend=vector_backend,
        dimension=chosen_embedder.dimension,
        qdrant_location=qdrant_location or ":memory:",
    )
    return MemoryEngine(
        store,
        embedder=chosen_embedder,
        vector_index=index,
        bus=bus,
        backend_report=report,
    )


__all__ = [
    "BLOCK_ORDER",
    "COMPRESS_CHAR_THRESHOLD",
    "COMPRESS_TURN_THRESHOLD",
    "COMPRESSION_STAGES",
    "ContextBlock",
    "MemoryContext",
    "MemoryEngine",
    "RANK_WEIGHTS",
    "RECENCY_HALF_LIFE_DAYS",
    "SCOPE_FIT",
    "SEMANTIC_STRONG",
    "build_memory_engine",
    "rank_score",
]
