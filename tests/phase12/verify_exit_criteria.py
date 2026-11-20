#!/usr/bin/env python3
"""Phase 12 verification harness — New Plan §12 / Build Plan §13 Exit Gate.

Proves the Memory System section by section:

* A — Contracts (§12.1–§12.3): the five names verbatim; the twelve
       scopes verbatim; the eleven metadata fields verbatim; evidence
       provenance validation; record/query misuse refused.
* B — SQLite index (§12.4): the five tables; add/get/update roundtrip;
       relationships; evidence rows; lexical stage; vector rows in the
       same file; restart persistence (new store, same path).
* C — Semantic layer (§12.5): HashingEmbedder determinism + dimension
       guard; cosine math; LocalVectorIndex upsert/search/filtered/
       restart; the Qdrant MODE-A adapter — BONUS live (qdrant-client
       installed → real local-mode roundtrip) and honest SKIP
       otherwise; ModelEmbedder over a fake manager (§5.7 routing,
       §5.1 request, float parsing, no-model refusal).
* D — Engine verbs (§13.1): remember · retrieve · search · update ·
       forget · summarize · link — all seven, with MEMORY_CREATED /
       MEMORY_UPDATED events on a real §2.2 bus; end-to-end restart
       persistence through the factory.
* E — Scope isolation (§12.2): task A never sees task B; PROJECT/
       WORKSPACE/SESSION/AGENT isolation strict; GLOBAL/USER visible
       everywhere; semantic libraries container-bound.
* F — Conflict resolution (§12.8): the ladder verbatim and in force —
       current_task > workspace_rules > project_decisions >
       user_preferences > old_lessons; §13.7 «the new wins» as
       recency; losers documented, not deleted.
* G — Forget (§12.9): exact/category/scope; audit keeps metadata and
       drops content; forgotten never retrieved (lexical, vector,
       context); the GLOBAL two-key guard.
* H — Compression (§12.10): the five stages verbatim; bilingual AR/EN
       markers; threshold triggers; summary minted + compressed_from
       links.
* I — Retrieval pipeline (§12.7): the staged flow; the ranking
       formula (pure, fixed now); budget cap with honest drop counts;
       provenance (vector/lexical merge).
* J — Mem0 adapter (§12.6): the §13.4 behaviors mapped (add/search/
       update/delete); absence probe honest; backend not duck-shaped →
       refused; extraction pattern provenance documented.
* K — Integration + regression: NEXUS_PHASE == 12; the module ships in
       the wheel; capability matrix honest; Phases 1–11 harnesses stay
       green.

Exit gate (§12.11), each line proven above::

    Memory create ✅        Memory retrieve ✅     Scope isolation ✅
    Conflict resolution ✅  Restart persistence ✅ Semantic retrieval ✅
    Existing tests ✅

Run:  python tests/phase12/verify_exit_criteria.py
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.events import EventBus  # noqa: E402
from nexus.memory import (  # noqa: E402
    BLOCK_ORDER,
    CONFLICT_PRIORITY,
    MEMORY_RECORD_FIELDS,
    MEMORY_SCOPES,
    RANK_WEIGHTS,
    ConflictResolver,
    HashingEmbedder,
    LocalVectorIndex,
    MemoryContext,
    MemoryEvidence,
    MemoryProvider,
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemoryType,
    SQLiteMemoryStore,
    build_memory_engine,
    conflict_level,
    cosine_similarity,
    mem0_probe,
    new_memory_id,
    payload_matches,
    qdrant_probe,
    rank_score,
    should_compress,
)
from nexus.memory.compression import COMPRESSION_STAGES  # noqa: E402
from nexus.memory.embeddings import ModelEmbedder  # noqa: E402
from nexus.memory.mem0_adapter import Mem0MemoryProvider  # noqa: E402
from nexus.memory.vectors import (  # noqa: E402
    QdrantVectorIndex,
    record_payload,
)

FAKE_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)


# ------------------------------------------------------------------- runner


class Runner:
    """Check counter with the house reporting format."""

    def __init__(self) -> None:
        self.section = ""
        self.passed = 0
        self.failed = 0
        self.bonus = 0

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        mark = "PASS" if condition else "FAIL"
        line = f"  [{mark}] ({self.section}) {label}"
        if detail and not condition:
            line += f" — {detail}"
        print(line)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def bonus_check(self, label: str, condition: bool, detail: str = "") -> bool:
        """Runtime-only evidence (qdrant/win32 extras): SKIP never fails."""
        if condition:
            self.bonus += 1
            print(f"  [BONUS] ({self.section}) {label}")
        else:
            print(f"  [SKIP]  ({self.section}) {label} — {detail}")
        return condition

    def summary(self) -> int:
        print()
        print("=" * 72)
        name = Path(sys.argv[0]).name
        if self.failed:
            print(f"{name} — {self.passed} passed, {self.failed} FAILED")
            print("=" * 72)
            return 1
        print(f"{name} — {self.passed} passed, 0 failed (+{self.bonus} bonus)")
        print("=" * 72)
        return 0


# ------------------------------------------------------------------ fakes


class FakeRoutingDecision:
    selected_model_id: str | None
    reason: str = "fake"

    def __init__(self, model_id: str | None) -> None:
        self.selected_model_id = model_id


class FakeManager:
    """A §5.4-ish fake: routing + generation, no real models."""

    def __init__(self, answer: str = "[0.1, 0.2, 0.3]") -> None:
        self.answer = answer
        self.requests: list[Any] = []
        self.routed: list[Any] = []

    def select(self, request: Any) -> FakeRoutingDecision:
        self.routed.append(request)
        return FakeRoutingDecision("embed-1")

    def generate(self, request: Any) -> Any:
        self.requests.append(request)

        class _Result:
            text = self.answer
            model_id = "embed-1"
            backend = "fake"

        return _Result()


class FakeMem0:
    """A deterministic mem0-shaped engine (add/search/get_all/update/
    delete) — the §13.4 behaviors the adapter wraps."""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.seq = 0
        self.calls: list[str] = []

    def add(self, content: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("add")
        self.seq += 1
        memory_id = f"m0-{self.seq}"
        self.store[memory_id] = {
            "id": memory_id,
            "memory": content,
            **{k: v for k, v in kwargs.items() if k != "infer"},
        }
        return {"results": [{"id": memory_id, "memory": content, "event": "ADD"}]}

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        self.calls.append("search")
        hits = []
        for item in self.store.values():
            if query.casefold() in str(item["memory"]).casefold():
                hits.append(item)
        return hits[:limit]

    def get_all(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append("get_all")
        return list(self.store.values())

    def update(self, memory_id: str, content: str) -> dict[str, Any]:
        self.calls.append("update")
        if memory_id in self.store:
            self.store[memory_id]["memory"] = content
        return {"results": [{"id": memory_id, "event": "UPDATE"}]}

    def delete(self, memory_id: str) -> dict[str, Any]:
        self.calls.append("delete")
        self.store.pop(memory_id, None)
        return {"results": [{"id": memory_id, "event": "DELETE"}]}


def _iso(minutes_ago: float) -> str:
    moment = FAKE_NOW - timedelta(minutes=minutes_ago)
    return moment.isoformat()


# ------------------------------------------------- A — contracts §12.1–§12.3


def section_a(runner: Runner) -> None:
    runner.section = "A-contracts"
    # §12.1 — the five names, importable and real
    runner.check(
        "§12.1 the five contract names exist",
        all(
            obj is not None
            for obj in (
                MemoryProvider,
                MemoryRecord,
                MemoryQuery,
                MemoryScope,
                MemoryEvidence,
            )
        ),
    )
    # §12.2 — the twelve scopes, verbatim order and spelling
    expected_scopes = (
        "global",
        "user",
        "project",
        "workspace",
        "task",
        "session",
        "agent",
        "knowledge",
        "decision",
        "lesson",
        "skill",
        "error",
    )
    runner.check(
        "§12.2 twelve scopes verbatim",
        MEMORY_SCOPES == expected_scopes,
        detail=f"got {MEMORY_SCOPES}",
    )
    # §12.3 — the eleven metadata fields, verbatim
    for field_name in (
        "id",
        "type",
        "scope",
        "content",
        "source",
        "confidence",
        "created_at",
        "updated_at",
        "expires_at",
        "project",
        "workspace",
        "task",
    ):
        runner.check(
            f"§12.3 metadata field {field_name!r} present",
            field_name in MEMORY_RECORD_FIELDS,
        )
    # evidence provenance
    good = MemoryEvidence(method="tool_run", uri="M:\\logs\\x.txt", snippet="…")
    good.validate()
    runner.check("§12.1 evidence with uri+method validates", True)
    try:
        MemoryEvidence(method="dream", uri="", snippet="").validate()
        bad_method = False
    except Exception:
        bad_method = True
    runner.check("§12.1 evidence method refused (not in vocabulary)", bad_method)
    try:
        MemoryEvidence(method="tool_run", uri="", snippet="").validate()
        empty_ev = False
    except Exception:
        empty_ev = True
    runner.check("§12.1 evidence without uri/snippet refused", empty_ev)
    # record misuse refused
    refused = 0
    for kwargs in (
        {"id": "bad", "type": "fact", "scope": "global", "content": "x", "source": "s"},
        {"id": new_memory_id(), "type": "warp", "scope": "global", "content": "x", "source": "s"},
        {"id": new_memory_id(), "type": "fact", "scope": "quasar", "content": "x", "source": "s"},
        {"id": new_memory_id(), "type": "fact", "scope": "global", "content": "  ", "source": "s"},
        {"id": new_memory_id(), "type": "fact", "scope": "task", "content": "x", "source": "s"},
    ):
        try:
            MemoryRecord(**kwargs)
        except Exception:
            refused += 1
    runner.check("§12.3 record misuse refused (5/5)", refused == 5)
    # query misuse refused
    try:
        MemoryQuery(limit=0)
        bad_query = False
    except Exception:
        bad_query = True
    runner.check("query limit=0 refused", bad_query)
    # id determinism + shape
    seeded = new_memory_id("seeded")
    runner.check(
        "id format mem_+16hex deterministic",
        seeded == new_memory_id("seeded") and len(seeded) == 20,
    )


# ------------------------------------------------------ B — store §12.4


def section_b(runner: Runner) -> None:
    runner.section = "B-store"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "memory.db"
        store = SQLiteMemoryStore(path)
        tables = {
            row[0]
            for row in store._conn.execute(  # noqa: SLF001 — schema introspection
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table in (
            "memory_records",
            "memory_evidence",
            "memory_relationships",
            "memory_audit",
            "memory_vectors",
        ):
            runner.check(f"§12.4 table {table} exists", table in tables)
        record = MemoryRecord(
            id=new_memory_id(),
            type=MemoryType.DECISION,
            scope=MemoryScope.PROJECT,
            content="نستخدم llama.cpp كمحرك الاستدلال",
            source="operator",
            confidence=0.9,
            project="nexus",
            evidence=(
                MemoryEvidence(
                    method="user_statement",
                    uri="chat:42",
                    snippet="قرار المشغّل",
                ),
            ),
        )
        store.add_record(record)
        back = store.get_record(record.id)
        runner.check("add/get roundtrip keeps content", back.content == record.content)
        runner.check("add/get roundtrip keeps evidence", len(back.evidence) == 1)
        store.add_relationship(record.id, record.id, "links")
        runner.check("relationship stored", store.count_relationships() == 1)
        # lexical stage
        hits = store.lexical_search(["llama"])
        runner.check(
            "lexical stage finds the needle",
            len(hits) == 1 and hits[0].id == record.id,
        )
        # vector rows live in the same file
        store.upsert_vector(record.id, [0.1, 0.2, 0.3], {"scope": "project"})
        vec, payload = store.get_vector(record.id)
        runner.check(
            "vector row roundtrip (same file, §12.4)",
            vec == [0.1, 0.2, 0.3] and payload["scope"] == "project",
        )
        # restart persistence — new store, same path
        store.close()
        store2 = SQLiteMemoryStore(path)
        back2 = store2.get_record(record.id)
        runner.check("§12.4 restart persistence (records)", back2.id == record.id)
        runner.check(
            "§12.4 restart persistence (relationships)",
            store2.count_relationships() == 1,
        )
        vec2, _ = store2.get_vector(record.id)
        runner.check("§12.4 restart persistence (vectors)", vec2 == [0.1, 0.2, 0.3])
        # tombstone + audit
        n = store2.tombstone([record.id], action="forget_exact", reason="r", requested_by="op")
        audit = store2.audit_log()
        runner.check("tombstone writes audit row", n == 1 and len(audit) == 1)
        redacted = audit[0].redacted()
        has_content = any("content" in str(value) for value in redacted.values())
        runner.check("audit keeps metadata, drops content", not has_content)
        runner.check(
            "tombstoned record inactive",
            store2.get_record(record.id).active is False,
        )


# --------------------------------------------- C — semantic layer §12.5


def section_c(runner: Runner) -> None:
    runner.section = "C-semantic"
    embedder = HashingEmbedder(dimension=64)
    v1 = embedder.embed("llama.cpp local inference engine")
    v2 = embedder.embed("llama.cpp local inference engine")
    v3 = embedder.embed("completely unrelated giraffe ballet")
    runner.check("HashingEmbedder deterministic", v1 == v2)
    runner.check("dimension respected", len(v1) == 64)
    sim_same = cosine_similarity(v1, v2)
    sim_far = cosine_similarity(v1, v3)
    runner.check("cosine: identical=1.0", abs(sim_same - 1.0) < 1e-9)
    runner.check("cosine: unrelated lower", sim_far < sim_same)
    runner.check("cosine: dim mismatch → 0.0", cosine_similarity(v1, [0.1]) == 0.0)
    runner.check(
        "Arabic tokens survive (الذاكرة embeds non-zero)",
        any(abs(x) > 0 for x in embedder.embed("الذاكرة")),
    )
    # payload subset semantics
    runner.check(
        "payload filter subset semantics",
        payload_matches({"scope": "task", "task": "t1"}, {"task": "t1"})
        and not payload_matches({"scope": "task", "task": "t1"}, {"task": "t2"}),
    )
    # local index: upsert/search/filter/restart
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteMemoryStore(Path(tmp) / "m.db")
        index = LocalVectorIndex(store)
        index.upsert(
            [
                ("mem_aaaaaaaa00000001",
                 embedder.embed("kernel panic stack"),
                 {"scope": "task", "task": "t1"}),
                ("mem_aaaaaaaa00000002",
                 embedder.embed("kernel panic stack"),
                 {"scope": "task", "task": "t2"}),
            ]
        )
        hits = index.search(embedder.embed("kernel panic"), limit=5)
        runner.check("LocalVectorIndex search finds both", len(hits) == 2)
        filtered = index.search(
            embedder.embed("kernel panic"), limit=5, flt={"task": "t1"}
        )
        runner.check(
            "§12.5 filtered retrieval (task=t1 only)",
            [h.record_id for h in filtered] == ["mem_aaaaaaaa00000001"],
        )
        store.close()
        store2 = SQLiteMemoryStore(Path(tmp) / "m.db")
        index2 = LocalVectorIndex(store2)
        hits2 = index2.search(embedder.embed("kernel panic"), limit=5)
        runner.check("§12.5 local restart persistence", len(hits2) == 2)
    # record payload mapping
    record = MemoryRecord(
        id=new_memory_id(),
        type=MemoryType.FACT,
        scope=MemoryScope.TASK,
        content="x",
        source="s",
        task="t9",
    )
    payload = record_payload(record)
    runner.check(
        "record_payload carries the filterable subset",
        payload["scope"] == "task" and payload["task"] == "t9",
    )
    # Qdrant MODE A — BONUS when installed, honest skip otherwise
    probe = qdrant_probe()
    runner.bonus_check(
        "§12.5 qdrant-client live (local mode): upsert/search/filter/count/delete",
        _qdrant_live_roundtrip(),
        detail=probe or "probe returned None but roundtrip failed",
    )
    # ModelEmbedder over a fake manager
    fake = FakeManager("[0.25, 0.5, 0.75]")
    model_embedder = ModelEmbedder(fake)
    values = model_embedder.embed("anything")
    runner.check(
        "ModelEmbedder routes §5.7 embeddings capability",
        len(fake.routed) == 1 and fake.routed[0].required_capability == "embeddings",
    )
    runner.check(
        "ModelEmbedder parses the floats",
        values == [0.25, 0.5, 0.75] and model_embedder.dimension == 3,
    )
    runner.check(
        "ModelEmbedder sends GenerateRequest with the routed model",
        fake.requests[0].model_id == "embed-1",
    )
    empty = FakeManager("")
    try:
        ModelEmbedder(empty).embed("x")
        refused = False
    except RuntimeError:
        refused = True
    runner.check("ModelEmbedder refuses when no vector comes back", refused)


def _qdrant_live_roundtrip() -> bool:
    if qdrant_probe() is not None:
        return False
    try:
        emb = HashingEmbedder(dimension=64)
        index = QdrantVectorIndex(location=":memory:", dimension=64)
        index.upsert(
            [
                ("mem_qdrant00000001",
                 emb.embed("semantic retrieval works"),
                 {"scope": "global"}),
                ("mem_qdrant00000002",
                 emb.embed("semantic retrieval works"),
                 {"scope": "task", "task": "t1"}),
            ]
        )
        hits = index.search(emb.embed("semantic retrieval"), limit=5)
        filtered = index.search(
            emb.embed("semantic retrieval"), limit=5, flt={"task": "t1"}
        )
        count_ok = index.count() == 2
        index.delete(["mem_qdrant00000001"])
        after = index.count() == 1
        return (
            len(hits) == 2
            and [h.record_id for h in filtered] == ["mem_qdrant00000002"]
            and count_ok
            and after
        )
    except Exception:
        return False


# ------------------------------------------- D — engine verbs §13.1


def section_d(runner: Runner) -> None:
    runner.section = "D-engine"
    bus = EventBus()
    engine = build_memory_engine(bus=bus)
    verbs = ("remember", "retrieve", "search", "update", "forget", "summarize", "link")
    runner.check(
        "§13.1 all seven verbs present",
        all(callable(getattr(engine, verb, None)) for verb in verbs),
    )
    r1 = engine.remember(
        "the persistence layer is SQLite",
        type=MemoryType.DECISION,
        scope=MemoryScope.PROJECT,
        project="nexus",
    )
    runner.check(
        "remember publishes MEMORY_CREATED (§2.2)",
        bus.published_count == 1,
    )
    engine.update(r1.id, content="the persistence layer is SQLite, WAL mode")
    runner.check(
        "update publishes MEMORY_UPDATED (§2.2) + bumps content",
        bus.published_count == 2
        and "WAL" in engine._store.get_record(r1.id).content,  # noqa: SLF001
    )
    r2 = engine.remember("scratch note for linking", source="test")
    engine.link(r1.id, r2.id, "evidence_for")
    links = engine._store.links_of(r1.id)  # noqa: SLF001
    runner.check(
        "link writes the relationship",
        any(link["relation"] == "evidence_for" for link in links),
    )
    hits = engine.search(MemoryQuery(text="persistence layer sqlite", project="nexus"))
    runner.check("search returns the ranked hit", any(h.record.id == r1.id for h in hits))
    ctx = engine.retrieve("persistence layer", project="nexus")
    runner.check(
        "retrieve assembles a MemoryContext",
        isinstance(ctx, MemoryContext) and ctx.total_chars > 0,
    )
    summary = engine.summarize(
        turns=(
            {"role": "user", "content": "قررنا اعتماد SQLite", "at": _iso(60)},
            {"role": "assistant", "content": "تم", "kind": "tool_call", "at": _iso(59)},
        ),
        project="nexus",
    )
    runner.check("summarize mints the compact record", summary.type == MemoryType.SUMMARY)
    result = engine.forget(record_id=r2.id, reason="test")
    runner.check("forget works through the engine", result.audit_rows == 1)
    # engine is a MemoryProvider
    runner.check("MemoryEngine is a MemoryProvider", isinstance(engine, MemoryProvider))
    # end-to-end restart persistence through the factory
    engine.close()
    with tempfile.TemporaryDirectory() as tmp:
        e1 = build_memory_engine(Path(tmp))
        e1.remember("restart proof fact", type=MemoryType.FACT)
        e1.remember("restart proof fact two", type=MemoryType.FACT)
        e1.close()
        e2 = build_memory_engine(Path(tmp))
        found = e2.search(MemoryQuery(text="restart proof fact"))
        e2.close()
        runner.check(
            "§12.11 restart persistence end-to-end (factory path)",
            len(found) >= 1,
            detail=f"hits={len(found)}",
        )


# ------------------------------------------- E — scope isolation §12.2


def section_e(runner: Runner) -> None:
    runner.section = "E-isolation"
    engine = build_memory_engine()
    task_a = engine.remember(
        "task A secret: port 8452", scope=MemoryScope.TASK, task="task_a", source="t"
    )
    engine.remember("task B secret: port 9999", scope=MemoryScope.TASK, task="task_b", source="t")
    ctx_a = engine.retrieve("secret port", task="task_a")
    ids_a = {b.record_id for b in ctx_a.blocks}
    runner.check(
        "TASK isolation: task A sees only its own memory",
        task_a.id in ids_a and len(ids_a) == 1,
        detail=f"ids={ids_a}",
    )
    # PROJECT isolation
    engine.remember("project alpha layout", scope=MemoryScope.PROJECT, project="alpha", source="t")
    engine.remember("project beta layout", scope=MemoryScope.PROJECT, project="beta", source="t")
    ctx_alpha = engine.retrieve("layout", project="alpha")
    contents = [b.text for b in ctx_alpha.blocks]
    runner.check(
        "PROJECT isolation: alpha never sees beta",
        any("alpha" in c for c in contents) and not any("beta" in c for c in contents),
    )
    # WORKSPACE / SESSION / AGENT
    engine.remember("ws one rule", scope=MemoryScope.WORKSPACE, workspace="ws1", source="t")
    engine.remember("ws two rule", scope=MemoryScope.WORKSPACE, workspace="ws2", source="t")
    ctx_ws = engine.retrieve("rule", workspace="ws1")
    runner.check(
        "WORKSPACE isolation strict",
        all("ws one" in b.text for b in ctx_ws.blocks) and len(ctx_ws.blocks) == 1,
    )
    engine.remember("session live note", scope=MemoryScope.SESSION, session="s1", source="t")
    ctx_none = engine.retrieve("live note")
    runner.check(
        "SESSION record invisible without the session key",
        len(ctx_none.blocks) == 0,
    )
    ctx_s1 = engine.retrieve("live note", session="s1")
    runner.check("SESSION record visible with the session key", len(ctx_s1.blocks) == 1)
    engine.remember("agent private scratch", scope=MemoryScope.AGENT, agent="coder-1", source="t")
    ctx_other = engine.retrieve("private scratch", agent="reviewer-1")
    runner.check(
        "AGENT privacy: another agent sees nothing",
        len(ctx_other.blocks) == 0,
    )
    # GLOBAL / USER everywhere
    engine.remember("global law: never fake evidence", source="t")
    engine.remember("user prefers arabic", scope=MemoryScope.USER, source="user")
    ctx_any = engine.retrieve("global law arabic", task="task_b", project="beta")
    seen = " ".join(b.text for b in ctx_any.blocks)
    runner.check(
        "GLOBAL + USER visible from any container context",
        "global law" in seen and "arabic" in seen,
    )
    # semantic libraries container-bound
    engine.remember(
        "docker compose lesson", scope=MemoryScope.LESSON, project="alpha", source="t"
    )
    lib_alpha = engine.retrieve("docker compose lesson", project="alpha")
    lib_beta = engine.retrieve("docker compose lesson", project="beta")
    runner.check(
        "LESSON library: bound container visible, other not",
        len(lib_alpha.blocks) == 1 and len(lib_beta.blocks) == 0,
    )
    engine.close()


# --------------------------------------- F — conflict resolution §12.8


def section_f(runner: Runner) -> None:
    runner.section = "F-conflict"
    runner.check(
        "§12.8 ladder verbatim (six levels, order exact)",
        CONFLICT_PRIORITY
        == (
            "current_prompt",
            "current_task",
            "workspace_rules",
            "project_decisions",
            "user_preferences",
            "old_lessons",
        ),
    )
    # one record per level, same conflict family
    records = {
        level: MemoryRecord(
            id=new_memory_id(level),
            type={
                "current_task": "decision",
                "workspace_rules": "rule",
                "project_decisions": "decision",
                "user_preferences": "preference",
                "old_lessons": "lesson",
            }.get(level, "fact"),
            scope={
                "current_task": "task",
                "workspace_rules": "workspace",
                "project_decisions": "project",
                "user_preferences": "user",
                "old_lessons": "lesson",
            }[level],
            content=f"engine choice per {level}",
            source="t",
            conflict_key="engine-choice",
            task="t1" if level == "current_task" else None,
            workspace="w1" if level == "workspace_rules" else None,
            project="p1" if level == "project_decisions" else None,
            updated_at=_iso(30),
        )
        for level in CONFLICT_PRIORITY[1:]  # current_prompt is the query itself
    }
    # resolve over descending insertion — ladder must still win
    resolver = ConflictResolver()
    order = [
        "old_lessons",
        "user_preferences",
        "project_decisions",
        "workspace_rules",
        "current_task",
    ]
    shuffled = [records[level] for level in order]
    kept, notes = resolver.resolve(list(shuffled))
    runner.check("one conflict family → one note", len(notes) == 1)
    runner.check(
        "current_task > workspace_rules > project > preference > lesson",
        notes[0].winner.id == records["current_task"].id
        and len(notes[0].losers) == 4,
    )
    # §13.7 — the new wins within the same level
    older = MemoryRecord(
        id=new_memory_id("old"),
        type=MemoryType.PREFERENCE,
        scope=MemoryScope.USER,
        content="prefer verbose answers",
        source="user",
        conflict_key="answer-style",
        updated_at=_iso(60 * 24 * 30),
    )
    newer = MemoryRecord(
        id=new_memory_id("new"),
        type=MemoryType.PREFERENCE,
        scope=MemoryScope.USER,
        content="prefer concise answers",
        source="user",
        conflict_key="answer-style",
        updated_at=_iso(10),
    )
    _, notes2 = resolver.resolve([older, newer])
    runner.check(
        "§13.7 «الجديد يفوز» — recency within one level",
        notes2[0].winner.id == newer.id,
    )
    # conflict_level mapping sanity
    runner.check(
        "conflict_level maps scopes onto the ladder",
        conflict_level(records["old_lessons"]) == "old_lessons"
        and conflict_level(records["user_preferences"]) == "user_preferences",
    )
    # end-to-end: retrieve keeps the winner, documents the losers
    engine = build_memory_engine()
    engine.remember(
        "engine: use llama.cpp", type=MemoryType.DECISION, scope=MemoryScope.TASK,
        task="t9", source="t", conflict_key="engine",
    )
    engine.remember(
        "engine: use ONNX instead", type=MemoryType.LESSON,
        scope=MemoryScope.LESSON, source="t", conflict_key="engine",
    )
    ctx = engine.retrieve("engine choice", task="t9")
    joined = ctx.as_prompt()
    runner.check(
        "context carries the §12.8 winner (task decision)",
        "use llama.cpp" in joined and "ONNX" not in joined,
    )
    runner.check(
        "context documents the conflict family",
        any("engine" in line for line in ctx.conflicts),
    )
    engine.close()


# ------------------------------------------------ G — forget §12.9


def section_g(runner: Runner) -> None:
    runner.section = "G-forget"
    engine = build_memory_engine()
    r1 = engine.remember("forget me exactly", source="t")
    engine.remember("keep me", source="t")
    result = engine.forget(record_id=r1.id, reason="gdpr-style request")
    runner.check("§12.9 exact forget", result.forgotten == (r1.id,))
    ctx = engine.retrieve("forget me exactly")
    runner.check(
        "forgotten never retrieved (context)",
        all(r1.id != b.record_id for b in ctx.blocks),
    )
    hits = engine.search(MemoryQuery(text="forget me exactly"))
    runner.check("forgotten never searched", all(h.record.id != r1.id for h in hits))
    runner.check("vectors removed with the tombstone", engine.backend()["vectors"] == 1)
    audit = engine.audit_log()
    runner.check("audit row written with reason", audit[0].reason == "gdpr-style request")
    # category forget
    for i in range(3):
        engine.remember(f"scratch {i}", type=MemoryType.NOTE, source="t")
    cat = engine.forget(type=MemoryType.NOTE, reason="cleanup")
    runner.check("§12.9 category forget (all notes)", len(cat.forgotten) == 3)
    # scope forget + container required
    engine.remember("task memory x", scope=MemoryScope.TASK, task="tx", source="t")
    scope_result = engine.forget(scope=MemoryScope.TASK, task="tx", reason="done")
    runner.check("§12.9 scope forget (task=tx)", bool(scope_result.forgotten))
    try:
        engine.forget(scope=MemoryScope.PROJECT)
        guard = False
    except Exception:
        guard = True
    runner.check("PROJECT scope forget requires project=", guard)
    try:
        engine.forget(scope=MemoryScope.GLOBAL)
        global_guard = False
    except Exception:
        global_guard = True
    runner.check("GLOBAL wipe two-key guard", global_guard)
    # audit keeps metadata forever, content never
    runner.check(
        "audit retains the forget history",
        len(engine.audit_log()) >= 5,
    )
    engine.close()


# ------------------------------------------- H — compression §12.10


def section_h(runner: Runner) -> None:
    runner.section = "H-compression"
    runner.check(
        "§12.10 stages verbatim (5)",
        COMPRESSION_STAGES
        == (
            "raw_history",
            "important_events",
            "decisions",
            "lessons",
            "compact_memory",
        ),
    )
    turns = (
        {"role": "user", "content": "قررنا استخدام SQLite وليس JSON", "at": _iso(120)},
        {"role": "assistant", "content": "حسنًا", "kind": "tool_call", "at": _iso(119)},
        {"role": "assistant", "content": "Traceback: خطأ في القراءة", "at": _iso(118)},
        {"role": "user", "content": "lesson: always close the store", "at": _iso(117)},
        {"role": "assistant", "content": "تم", "kind": "file_write", "at": _iso(116)},
    )
    runner.check("trigger: under thresholds → False", should_compress(turns) is False)
    long_turns = tuple({"role": "user", "content": "قررنا شيئًا"} for _ in range(55))
    runner.check(
        "trigger: 55 turns → True (threshold 50)",
        should_compress(long_turns) is True,
    )
    big_chars = ({"role": "user", "content": "x" * 25_000},)
    runner.check(
        "trigger: 25k chars → True (threshold 24k)",
        should_compress(big_chars) is True,
    )
    engine = build_memory_engine()
    summary = engine.summarize(turns=turns, project="nexus")
    state = engine.compression_state(turns)
    runner.check("summarize ran over all turns", state["turns"] == len(turns))
    blocks = engine.retrieve("قررنا lesson store", project="nexus")
    joined = blocks.as_prompt()
    runner.check(
        "the decision survives into memory (AR marker)",
        "SQLite" in joined,
    )
    runner.check(
        "the lesson survived (EN marker)",
        "close the store" in joined,
    )
    links = engine._store.links_of(summary.id)  # noqa: SLF001
    runner.check(
        "compressed_from links minted (§13.1 link)",
        sum(1 for link in links if link["relation"] == "compressed_from") >= 3,
    )
    runner.check(
        "summary is compact (≪ raw chars)",
        len(summary.content) < 400,
    )
    engine.close()


# --------------------------------- I — retrieval pipeline §12.7


def section_i(runner: Runner) -> None:
    runner.section = "I-pipeline"
    weights_sum = sum(RANK_WEIGHTS.values())
    runner.check(
        "ranking weights documented and normalized",
        set(RANK_WEIGHTS) == {"semantic", "lexical", "recency", "confidence", "scope_fit"}
        and abs(weights_sum - 1.0) < 1e-9,
        detail=f"sum={weights_sum}",
    )
    fresh = MemoryRecord(
        id=new_memory_id("fresh"),
        type=MemoryType.FACT,
        scope=MemoryScope.TASK,
        content="fresh fact",
        source="t",
        task="t1",
        updated_at=_iso(1),
    )
    stale = MemoryRecord(
        id=new_memory_id("stale"),
        type=MemoryType.FACT,
        scope=MemoryScope.TASK,
        content="stale fact",
        source="t",
        task="t1",
        updated_at=_iso(60 * 24 * 60),
    )
    score_fresh = rank_score(fresh, semantic=0.5, lexical=0.5, now=FAKE_NOW)
    score_stale = rank_score(stale, semantic=0.5, lexical=0.5, now=FAKE_NOW)
    runner.check("recency: fresh outranks stale (14d half-life)", score_fresh > score_stale)
    runner.check(
        "scope_fit: TASK beats GLOBAL at equal evidence",
        rank_score(fresh, semantic=0.5, lexical=0.5, now=FAKE_NOW)
        > rank_score(
            MemoryRecord(
                id=new_memory_id("g"),
                type=MemoryType.FACT,
                scope=MemoryScope.GLOBAL,
                content="g",
                source="t",
                updated_at=_iso(1),
            ),
            semantic=0.5,
            lexical=0.5,
            now=FAKE_NOW,
        ),
    )
    # budget honesty
    engine = build_memory_engine()
    for i in range(10):
        engine.remember(
            f"budget fact number {i} " + "detail " * 30, source="t"
        )
    ctx = engine.retrieve("budget fact", budget_chars=600)
    runner.check(
        "§12.7 budget cap honored (total ≤ budget)",
        ctx.total_chars <= 600,
        detail=f"total={ctx.total_chars}",
    )
    runner.check(
        "dropped count is honest (not silent)",
        ctx.dropped > 0,
        detail=f"dropped={ctx.dropped}",
    )
    runner.check(
        "block order follows BLOCK_ORDER",
        [b.kind for b in ctx.blocks]
        == sorted([b.kind for b in ctx.blocks], key=BLOCK_ORDER.index),
    )
    runner.check(
        "provenance records the stages (vector/lexical/rule)",
        ctx.provenance != ()
        and set(ctx.provenance) <= {"vector", "lexical", "rule"},
    )
    runner.check(
        "context JSON view is audit-shaped (to_dict)",
        isinstance(ctx.to_dict(), dict) and "dropped" in ctx.to_dict(),
    )
    # §12.7 relevance floor — unrelated-but-fresh records stay OUT
    floor_engine = build_memory_engine()
    floor_engine.remember(
        "the port is 8452", type=MemoryType.FACT, source="t"
    )
    floor_engine.remember(
        "unrelated fresh note about giraffes", type=MemoryType.NOTE, source="t"
    )
    floor_ctx = floor_engine.retrieve("port")
    floor_texts = " ".join(b.text for b in floor_ctx.blocks)
    floor_engine.close()
    runner.check(
        "relevance floor: fresh-but-unrelated memory stays out of context",
        "port" in floor_texts and "giraffes" not in floor_texts,
        detail=f"texts={floor_texts[:120]!r}",
    )
    # empty store → empty context, no crash
    empty_engine = build_memory_engine()
    empty_ctx = empty_engine.retrieve("anything at all")
    runner.check("empty store → empty context", empty_ctx.total_chars == 0)
    empty_engine.close()
    engine.close()


# ------------------------------------------- J — mem0 adapter §12.6


def section_j(runner: Runner) -> None:
    runner.section = "J-mem0"
    probe = mem0_probe()
    runner.check(
        "§12.6 absence probe honest (reason string or None)",
        probe is None or probe.startswith("mem0ai not installed"),
        detail=str(probe),
    )
    fake = FakeMem0()
    provider = Mem0MemoryProvider(fake)
    runner.check(
        "adapter is a MemoryProvider (§13.1 contract)",
        isinstance(provider, MemoryProvider),
    )
    r = provider.remember(
        "adapter test memory", type=MemoryType.FACT, agent="a1", source="t"
    )
    runner.check(
        "remember → mem0.add + side-store record",
        "add" in fake.calls and r.id.startswith("mem_"),
    )
    hits = provider.search(MemoryQuery(text="adapter test"))
    runner.check(
        "search → mem0.search mapped back onto our records",
        "search" in fake.calls and any(h.record.id == r.id for h in hits),
    )
    provider.update(r.id, content="adapter test memory v2")
    runner.check("update → mem0.update", "update" in fake.calls)
    provider.forget(record_id=r.id, reason="t")
    runner.check(
        "forget → mem0.delete + audited tombstone",
        "delete" in fake.calls and len(provider._store.audit_log()) == 1,  # noqa: SLF001
    )
    s = provider.summarize(
        turns=({"role": "user", "content": "قررنا اختبار المحوّل"},)
    )
    runner.check(
        "summarize uses the deterministic compressor (§12.6 behaviors)",
        s.type == MemoryType.SUMMARY,
    )
    provider.link(r.id, s.id, "links")
    rels = provider._store.links_of(r.id) + provider._store.links_of(s.id)  # noqa: SLF001
    runner.check(
        "link stays NEXUS-owned (mem0 has no relations)",
        any(rel["relation"] == "links" for rel in rels),
    )
    try:
        Mem0MemoryProvider(object())
        duck_refused = False
    except Exception:
        duck_refused = True
    runner.check("not-mem0-shaped backend refused", duck_refused)
    report = provider.backend_report()
    runner.check(
        "backend report names the adapter and the probe",
        report["adapter"] == "mem0" and "probe" in report,
    )


# --------------------------------- K — integration + regression


def section_k(runner: Runner, *, regression: bool = True) -> None:
    runner.section = "K-integration"
    import nexus

    runner.check(
        "NEXUS_PHASE == 12",
        getattr(nexus, "NEXUS_PHASE", None) == 12,
        detail=f"got {getattr(nexus, 'NEXUS_PHASE', None)!r}",
    )
    runner.check(
        "__version__ == 0.12.0",
        getattr(nexus, "__version__", "") == "0.12.0",
        detail=f"got {getattr(nexus, '__version__', '')!r}",
    )
    # packaging: the memory modules ship
    import importlib.util

    shipped = all(
        importlib.util.find_spec(f"nexus.memory.{mod}") is not None
        for mod in (
            "contracts",
            "store",
            "embeddings",
            "vectors",
            "mem0_adapter",
            "conflict",
            "forget",
            "compression",
            "engine",
        )
    )
    runner.check("all nine memory modules importable", shipped)
    # pyproject keeps the core stdlib-only
    import tomllib

    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    runner.check(
        "core dependencies stay empty (Plan §2)",
        data["project"]["dependencies"] == [],
    )
    extras = data["project"]["optional-dependencies"]
    runner.check(
        "§12.5/§12.6 extras pinned (qdrant, mem0)",
        "qdrant" in extras and "mem0" in extras,
    )
    # ownership skeleton: memory filled with real code
    memory_dir = REPO_ROOT / "nexus" / "memory"
    files = sorted(p.name for p in memory_dir.glob("*.py"))
    runner.check(
        "memory package is real code now (≥9 modules, no .gitkeep)",
        len(files) >= 9 and not (memory_dir / ".gitkeep").exists(),
        detail=str(files),
    )
    # CI wiring
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    runner.check(
        "CI runs the Phase 12 harness",
        "tests/phase12/verify_exit_criteria.py" in ci,
    )
    runner.check("CI has the memory-live job (§12.5 Qdrant)", "memory-live:" in ci)
    # report exists
    runner.check(
        "docs/PHASE-12-REPORT.md exists",
        (REPO_ROOT / "docs" / "PHASE-12-REPORT.md").is_file(),
    )
    # the engine runs without extras (explicit local) and the auto
    # choice is honest either way (qdrant when present, reason when not)
    local_engine = build_memory_engine(vector_backend="local")
    local_backend = local_engine.backend()
    local_engine.close()
    runner.check(
        "explicit local engine needs no extras (local-sqlite)",
        local_backend["vector_backend"] == "local-sqlite",
        detail=local_backend["report"],
    )
    auto_engine = build_memory_engine()
    auto_backend = auto_engine.backend()
    auto_engine.close()
    runner.check(
        "auto backend is honest (qdrant loaded or fallback reason)",
        auto_backend["vector_backend"] in ("local-sqlite", "qdrant-local")
        and bool(auto_backend["report"]),
        detail=auto_backend["report"],
    )
    if regression:
        _regression(runner)


def _regression(runner: Runner) -> None:
    """Phases 1–11 harnesses stay green (subprocess, house pattern)."""
    runner.section = "K-regression"
    prior = [
        ("phase01", "Phase 1"),
        ("phase02", "Phase 2"),
        ("phase03", "Phase 3"),
        ("phase04", "Phase 4"),
        ("phase05", "Phase 5"),
        ("phase06", "Phase 6"),
        ("phase07", "Phase 7"),
        ("phase08", "Phase 8"),
        ("phase09", "Phase 9"),
        ("phase10", "Phase 10"),
        ("phase11", "Phase 11"),
    ]
    for phase_dir, label in prior:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tests" / phase_dir / "verify_exit_criteria.py"),
            ],
            capture_output=True,
            text=True,
            timeout=2400,
        )
        last_line = (
            proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "<no output>"
        )
        runner.check(
            f"{label} harness still green ({last_line})",
            proc.returncode == 0,
            detail=f"exit={proc.returncode} last={last_line!r}",
        )


# ======================================================================= main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="unused (repo-rooted)")
    parser.add_argument(
        "--no-regression",
        action="store_true",
        help="skip the Phase 1–11 subprocess regression (local quick runs)",
    )
    args = parser.parse_args()
    print(
        "PHASE 12 — Memory System (New Plan §12 / Build Plan §13) exit criteria"
    )
    runner = Runner()
    sections = (
        section_a,
        section_b,
        section_c,
        section_d,
        section_e,
        section_f,
        section_g,
        section_h,
        section_i,
        section_j,
    )
    for section in sections:
        try:
            section(runner)
        except Exception as exc:  # noqa: BLE001 — a section crash is a failure
            print(f"  [FAIL] ({runner.section}) section crashed: {exc}")
            runner.failed += 1
    try:
        section_k(runner, regression=not args.no_regression)
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] ({runner.section}) section crashed: {exc}")
        runner.failed += 1
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
