"""Mem0 adapter (New Plan §12.6 — Final Build Plan §13.4, MODE B).

Repository: **mem0ai/mem0** (Apache-2.0), staged at
``vendor-staging/phase-12/mem0`` — *persistent memory engine
candidate*. Its behaviors we adapt (Plan §54 cycle recorded in
docs/REPOSITORY-INTEGRATION.md §12):

* **memory extraction** — mem0's ``add(infer)`` pulls structured facts
  out of raw conversation; NEXUS's deterministic counterpart lives in
  :mod:`nexus.memory.compression` (§12.10) and stays the default —
  the adapter delegates extraction to mem0 *only* when a real,
  LLM-backed mem0 is injected;
* **retrieval patterns** — mem0's user/session/agent scoping maps onto
  our §12.2 containers; this adapter translates them 1:1;
* **update/delete** — mem0's memory maintenance ops ride the §13.1
  verbs.

The architecture invariant (Plan §61: *NEXUS owns Memory semantics*)
shapes the design: this provider implements our
:class:`~nexus.memory.contracts.MemoryProvider` — the seven §13.1
verbs — over a duck-typed mem0 backend, while a side
:class:`~nexus.memory.store.SQLiteMemoryStore` keeps the NEXUS-owned
metadata (ids, scopes, links, §12.9 audit). Swapping mem0 for any
other engine later means writing one more adapter, nothing else.

Absence is reported honestly (:func:`mem0_probe`) — the core runs
stdlib-only, ``pip install nexus-core[mem0]`` is optional.

مُكيَّف Mem0 — سلوكيات الاستخراج والاسترجاع خلف عقودنا؛
الغياب يُبلَّغ ولا يُخفى.

Stdlib only (mem0ai is optional).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .compression import MemoryCompressor
from .contracts import (
    ForgetResult,
    InvalidMemoryError,
    MemoryEvidence,
    MemoryProvider,
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemorySearchHit,
    MemoryType,
    new_memory_id,
    scope_visible,
)
from .engine import MemoryContext
from .forget import ForgetOps
from .store import SQLiteMemoryStore


def mem0_probe() -> str | None:
    """None when ``mem0`` is importable, else the honest reason."""
    try:
        import mem0  # type: ignore[import-not-found]  # noqa: F401 — probe
    except ImportError as exc:
        return f"mem0ai not installed: {exc}"
    return None


#: mem0 scope → our §12.2 container mapping (the §13.4 pattern).
MEM0_SCOPE_MAP: dict[str, tuple[str, str]] = {
    # mem0 key      → (record scope, container field)
    "user_id": (MemoryScope.USER, "agent"),
    "agent_id": (MemoryScope.AGENT, "agent"),
    "run_id": (MemoryScope.SESSION, "session"),
}


class Mem0MemoryProvider(MemoryProvider):
    """§12.6 adapter — the seven §13.1 verbs over a mem0 backend.

    ``backend`` — any mem0-like object (duck-typed: ``add``, ``search``,
    ``get_all``, ``update``, ``delete``). The real ``mem0.Memory`` when
    installed; a deterministic fake in tests. The NEXUS-owned side
    store keeps ids/scopes/links/audit so semantics stay ours (§61)
    even when the engine is theirs.
    """

    def __init__(
        self,
        backend: Any,
        store: SQLiteMemoryStore | None = None,
        *,
        infer: bool = False,
    ) -> None:
        for verb in ("add", "search", "get_all", "update", "delete"):
            if not callable(getattr(backend, verb, None)):
                raise InvalidMemoryError(
                    f"mem0 backend is missing {verb!r} — not a mem0-shaped engine"
                )
        self._backend: Any = backend
        self._store = store or SQLiteMemoryStore(":memory:")
        self._forget = ForgetOps(self._store)
        self._compressor = MemoryCompressor()
        self._infer = infer

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
        """Write through both layers: mem0 (engine) + side store (ours)."""
        mem0_filter = _mem0_filter(project, workspace, task, session, agent)
        self._backend.add(
            content,
            infer=self._infer,
            metadata={"type": type, "scope": scope, "source": source},
            **mem0_filter,
        )
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
        return record

    # ------------------------------------------------------------- search

    def search(self, query: MemoryQuery) -> list[MemorySearchHit]:
        """mem0's search, mapped back onto our records + ranking shape."""
        self._store.sweep_expired()
        results: Sequence[Any] = self._backend.search(
            query.text, limit=query.limit
        ) if query.text else []
        theirs: dict[str, str] = {}
        for item in results:
            memory_id = _field(item, "id")
            text = _field(item, "memory") or _field(item, "content") or ""
            if memory_id and text:
                theirs[text] = str(memory_id)
        hits: list[MemorySearchHit] = []
        for record in self._store.iter_records(active_only=True):
            if not scope_visible(record, query):
                continue
            score = 1.0 if record.content in theirs else 0.0
            if query.text and query.text.casefold() in record.content.casefold():
                score = max(score, 0.9)
            if score <= 0.0:
                continue
            hits.append(
                MemorySearchHit(
                    record=record,
                    score=score,
                    lexical=score,
                    provenance=("mem0",) if record.content in theirs else ("side",),
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.record.id))
        return hits[: query.limit]

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
        """Search + assemble a §12.7-shaped context (local assembly —
        mem0 returns hits, the context contract stays NEXUS's)."""
        query = MemoryQuery(
            text=prompt,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
            agent=agent,
            limit=limit,
        )
        hits = self.search(query)
        context = MemoryContext(prompt=prompt, budget_chars=budget_chars)
        used = 0
        dropped = 0
        for hit in hits:
            text = f"{hit.record.content} (source: {hit.record.source})"
            if used + len(text) > budget_chars:
                dropped += 1
                continue
            used += len(text)
            context.blocks.append(
                _block(hit.record.id, text, hit.record.type)
            )
        context.dropped = dropped
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
        record = self._store.get_record(record_id)
        if not record.active:
            raise InvalidMemoryError(f"record {record_id} is forgotten — cannot update")
        new_content = content if content is not None else record.content
        if content is not None:
            self._backend.update(record_id, new_content)
        return self._store.update_record(
            record_id,
            content=content,
            confidence=confidence,
            expires_at=expires_at,
        )

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
        """§12.9 through both layers: mem0 delete + our audited tombstone."""
        if record_id is not None:
            self._backend.delete(record_id)
            return self._forget.forget_exact(
                record_id, reason=reason, requested_by=requested_by
            )
        if type is not None:
            return self._forget.forget_category(
                type,
                project=project,
                workspace=workspace,
                task=task,
                reason=reason,
                requested_by=requested_by,
            )
        if scope is not None:
            return self._forget.forget_scope(
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
        raise InvalidMemoryError("forget needs record_id= or type= or scope= (§12.9)")

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
        """§12.10 over the side store (mem0 has no summarize op — the
        extraction *behavior* is what we took from it, and the local
        compressor implements it deterministically)."""
        if turns:
            extracted, summary = self._compressor.summarize(
                [dict(turn) for turn in turns]
            )
        elif record_ids:
            records = [self._store.get_record(rid) for rid in record_ids]
            pseudo = [
                {"role": "memory", "content": r.content, "kind": "artifact",
                 "at": r.updated_at}
                for r in records
            ]
            extracted, summary = self._compressor.summarize(pseudo)
        else:
            raise InvalidMemoryError("summarize needs turns= or record_ids=")
        for item in extracted:
            item.record.project = project or item.record.project
            item.record.task = task or item.record.task
            self._store.add_record(item.record)
        summary.task = task or summary.task
        summary.project = project or summary.project
        self._store.add_record(summary)
        for item in extracted:
            self._store.add_relationship(
                summary.id, item.record.id, "compressed_from"
            )
        return summary

    # ---------------------------------------------------------------- link

    def link(
        self,
        record_id: str,
        related_id: str,
        relation: str = "links",
    ) -> None:
        """§13.1 link — NEXUS-owned (mem0 has no relation graph)."""
        self._store.get_record(record_id)
        self._store.get_record(related_id)
        self._store.add_relationship(record_id, related_id, relation)

    # ------------------------------------------------------------ plumbing

    def backend_report(self) -> dict[str, Any]:
        probe = mem0_probe()
        return {
            "adapter": "mem0",
            "real_mem0": probe is None,
            "probe": probe or "mem0 importable",
            "infer": self._infer,
            "records": self._store.count_records(),
        }


# ---------------------------------------------------------------- helpers


def _field(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def _mem0_filter(
    project: str | None,
    workspace: str | None,
    task: str | None,
    session: str | None,
    agent: str | None,
) -> dict[str, str]:
    """mem0's scope kwargs — the §13.4 user/agent/run pattern."""
    flt: dict[str, str] = {}
    if agent:
        flt["agent_id"] = agent
    if session:
        flt["run_id"] = session
    if project:
        flt["app"] = project  # mem0's app/project partition
    _ = (workspace, task)  # ours alone — the side store carries them
    return flt


def _block(record_id: str, text: str, record_type: str):
    from .engine import ContextBlock

    return ContextBlock(kind=record_type, text=text, record_id=record_id)


__all__ = [
    "MEM0_SCOPE_MAP",
    "Mem0MemoryProvider",
    "mem0_probe",
]
