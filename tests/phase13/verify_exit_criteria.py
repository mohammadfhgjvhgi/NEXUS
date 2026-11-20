#!/usr/bin/env python3
"""Phase 13 verification harness — New Plan §13 Exit Gate.

Proves the Learning System section by section:

* A — Contracts (§13.1/§13.2/§13.4): the six experience kinds
       verbatim; the Learning Record six fields verbatim; validation
       refuses misuse (ids, scopes, statuses, confidence bounds);
       signatures deterministic; skill candidate shape.
* B — Extractor (§13.1): one finished task → all six kinds; failure
       steps carry their own evidence; decisions, patterns, lessons;
       the skill-candidate mint.
* C — Store (§13.3 stage 5): four tables; experiences audit; record
       upsert/merge by signature; sequences; lexical search of
       pending lessons; restart persistence (new store, same file).
* D — Pipeline (§13.3): absorb runs the six stages; the evidence
       check refuses opinion (no evidence) — refused but never lost
       (audit keeps it); confidence rule monotone in evidence and
       repeats; promotion writes a REAL §12 engine record
       (source "learning", conflict_key the signature); re-learning
       merges (occurrences +1) and reinforces the §12 confidence.
* E — Skills (§13.4): Task A, Task B, Task C — same steps — the
       miner folds the pattern into a skill candidate (occurrences 3,
       evidence from each task); two repeats stay noise; the
       candidate promotes into the §12 engine as a SKILL record.
* F — Future retrieval (§13.3 last arrow): recall() surfaces both
       promoted (via the engine) and pending lessons; the §12.7
       retrieve() of a FUTURE task already carries the learned lesson.
* G — Restart persistence: file-rooted pipeline closed, reopened —
       records, skills, experiences survive; a re-run still merges.
* H — Events: a real §2.2 EventBus sees learning.record.created /
       learning.record.promoted / learning.skill.found.
* I — Honest degradation: no memory attached → promotion skipped,
       lessons stay pending, recall still answers (pending only).
* J — Learning ≠ memory: the same lesson re-learned is ONE record
       (dedupe by signature); the §12.8 ladder untouched — a newer
       operator memory outranks the learned lesson in a conflict.
* K — Integration + regression: NEXUS_PHASE ≥ 13; the module ships;
       the core stays stdlib-only; Phases 1–12 harnesses stay green.

Exit gate, each line proven above::

    Experience extraction ✅   Learning records ✅
    Evidence check ✅          Confidence + store ✅
    Skill candidate ✅         Future retrieval ✅
    Restart persistence ✅     Existing tests ✅

Run:  python tests/phase13/verify_exit_criteria.py [--no-regression]
Exit 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.events import EventBus  # noqa: E402
from nexus.learning import (  # noqa: E402
    EXPERIENCE_KINDS,
    LEARNING_RECORD_FIELDS,
    ExperienceExtractor,
    InvalidLearningError,
    LearningPipeline,
    LearningRecord,
    SkillCandidate,
    SQLiteLearningStore,
    build_learning_pipeline,
    confidence_for,
    lesson_signature,
    step_sequence_of,
    workflow_signature,
)
from nexus.memory import (  # noqa: E402
    MemoryEngine,
    MemoryQuery,
    MemoryScope,
    MemoryType,
    SQLiteMemoryStore,
)
from nexus.memory.contracts import MemoryEvidence  # noqa: E402

# ================================================================== runner


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


# ------------------------------------------------------------------ corpus


def ev(method: str = "tool_run", uri: str = "task:t1", snippet: str = "run log") -> MemoryEvidence:
    return MemoryEvidence(method=method, uri=uri, snippet=snippet)


def task_result(
    task_id: str,
    *,
    outcome: str = "success",
    summary: str = "opened the tunnel and verified the health check",
    steps: list[dict[str, Any]] | None = None,
    lesson: str = "",
    evidence: list[MemoryEvidence] | None = None,
    **containers: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "task_id": task_id,
        "outcome": outcome,
        "summary": summary,
        "steps": steps or [],
        "lesson": lesson,
        "evidence": evidence if evidence is not None else [ev(uri=f"task:{task_id}")],
    }
    result.update(containers)
    return result


REPEAT_STEPS = [
    {"name": "open_tunnel", "status": "ok"},
    {"name": "health_check", "status": "ok"},
    {"name": "auth_probe", "status": "ok"},
]


def repeat_workflow_task(task_id: str, project: str = "nexus") -> dict[str, Any]:
    """The §13.4 corpus: the SAME workflow, different tasks."""
    return task_result(
        task_id,
        outcome="success",
        summary="tunnel verified end to end",
        steps=[dict(s) for s in REPEAT_STEPS],
        project=project,
    )


# =============================================================== sections


def section_a(runner: Runner) -> None:
    """A — Contracts: §13.1/§13.2/§13.4 verbatim vocabularies."""
    runner.section = "A-contracts"
    runner.check(
        "the six §13.1 kinds verbatim",
        EXPERIENCE_KINDS
        == (
            "success",
            "failure",
            "decision",
            "pattern",
            "lesson",
            "skill_candidate",
        ),
        detail=f"got {EXPERIENCE_KINDS}",
    )
    verbatim_fields = (
        "experience_id",
        "lesson",
        "source_task",
        "evidence",
        "confidence",
        "scope",
    )
    runner.check(
        "the §13.2 six Learning Record fields verbatim",
        all(f in LEARNING_RECORD_FIELDS for f in verbatim_fields),
    )

    def refuse(fn: Any) -> bool:
        try:
            fn()
        except InvalidLearningError:
            return True
        return False

    base: dict[str, Any] = dict(
        id="les_abcd0123456789ef",
        experience_id="exp_abcd0123456789ef",
        lesson="verify the token before the first call",
        source_task="t-101",
        confidence=0.7,
        scope="lesson",
    )
    runner.check("record accepted in the honest shape", LearningRecord(**base) is not None)
    runner.check("bad id refused", refuse(lambda: LearningRecord(**{**base, "id": "nope"})))
    runner.check(
        "empty lesson refused", refuse(lambda: LearningRecord(**{**base, "lesson": "  "}))
    )
    runner.check(
        "unknown scope refused", refuse(lambda: LearningRecord(**{**base, "scope": "vibe"}))
    )
    runner.check(
        "bad status refused", refuse(lambda: LearningRecord(**{**base, "status": "maybe"}))
    )
    runner.check(
        "confidence out of bounds refused",
        refuse(lambda: LearningRecord(**{**base, "confidence": 1.5})),
    )
    runner.check(
        "signature deterministic",
        lesson_signature("same lesson", "lesson")
        == lesson_signature("Same Lesson ", "lesson")
        and lesson_signature("same lesson", "lesson")
        != lesson_signature("same lesson", "error"),
    )
    skill = SkillCandidate(
        id="skc_abcd0123456789ef",
        pattern=workflow_signature(("a", "b")),
        steps=("a", "b"),
        occurrences=3,
        source_tasks=("t1", "t2", "t3"),
    )
    runner.check(
        "§13.4 candidate: 3 repeats, evidence per task, wsig pattern",
        skill.occurrences == 3 and len(skill.source_tasks) == 3,
    )
    runner.check(
        "confidence never reaches 1.0 (corrigible by design)",
        confidence_for("lesson", evidence_methods=("tool_run", "test", "research"), occurrences=99)
        <= 0.95,
    )


def section_b(runner: Runner) -> None:
    """B — Extractor: one task → the six kinds."""
    runner.section = "B-extractor"
    extractor = ExperienceExtractor()
    result = task_result(
        "t-kinds",
        outcome="failure",
        summary="tunnel health failed — must fix token first, avoid retry loops",
        steps=[
            {"name": "health_check", "status": "error", "error": "401 unauthorized"},
            {"name": "retry", "status": "ok", "decision": True, "choice": "switch to t2"},
            {"name": "health_check", "status": "ok"},
            {"name": "auth_probe", "status": "ok"},
            {"name": "health_check", "status": "ok"},
            {"name": "auth_probe", "status": "ok"},
        ],
        lesson="always rotate the token before retrying the tunnel",
        evidence=[ev(uri="task:t-kinds")],
        project="nexus",
    )
    got = extractor.extract(result)
    kinds = {e.kind for e in got}
    runner.check(
        "failure extracted with the failing step's own evidence",
        "failure" in kinds
        and any("health_check" in e.summary for e in got if e.kind == "failure"),
    )
    runner.check(
        "decision extracted",
        "decision" in kinds and any("switch to t2" in e.summary for e in got),
    )
    runner.check(
        "explicit lesson extracted",
        any(e.kind == "lesson" and "rotate" in e.summary for e in got),
    )
    runner.check(
        "pattern extracted (health_check > auth_probe repeated in-task)",
        any(e.kind == "pattern" for e in got),
        detail=f"kinds={sorted(kinds)}",
    )
    runner.check("success NOT extracted from a failed task", "success" not in kinds)
    runner.check(
        "every experience carries the task, summary and containers",
        all(e.task_id == "t-kinds" and e.summary.strip() and e.project == "nexus" for e in got),
    )
    ok = extractor.extract(task_result("t-ok", outcome="success"))
    runner.check("success extracted from a successful task", any(e.kind == "success" for e in ok))
    minted = extractor.extract_skill_candidate(
        steps=("open_tunnel", "health_check", "auth_probe"),
        occurrences=3,
        source_tasks=("a", "b", "c"),
    )
    runner.check(
        "§13.4 mint: kind skill_candidate with per-task evidence",
        minted.kind == "skill_candidate" and len(minted.evidence) == 3,
    )
    runner.check(
        "sequence_of normalizes steps",
        step_sequence_of(result)
        == ("health_check", "retry", "health_check", "auth_probe", "health_check", "auth_probe"),
    )


def section_c(runner: Runner) -> None:
    """C — Store: the four tables, merge, restart."""
    runner.section = "C-store"
    root = Path(tempfile.mkdtemp(prefix="nexus-p13-store-"))
    store = SQLiteLearningStore(root / "learning.db")
    backend = store.backend()
    counts = backend["counts"]
    runner.check(
        "four tables, all empty, schema v1",
        set(counts)
        == {"experiences", "learning_records", "task_sequences", "skill_candidates"}
        and all(v == 0 for v in counts.values())
        and backend["schema_version"] == 1,
    )
    extractor = ExperienceExtractor()
    exp = extractor.extract(task_result("t-1", lesson="check the port first"))[0]
    store.add_experience(exp)
    record = LearningRecord(
        id="les_0000000000000001",
        experience_id=exp.id,
        lesson="check the port first",
        source_task="t-1",
        evidence=(ev(uri="task:t-1"),),
        confidence=0.7,
        scope="lesson",
    )
    store.add_record(record)
    runner.check("experience roundtrip", store.get_experience(exp.id) is not None)
    found = store.find_by_signature(record.signature)
    assert found is not None
    runner.check("record found by signature", found.id == record.id)
    found.confidence = 0.8
    store.update_record(found)
    reloaded = store.get_record(record.id)
    assert reloaded is not None
    runner.check("record update persists", reloaded.confidence == 0.8)
    store.record_sequence("t-1", ("a", "b", "c"), project="nexus")
    runner.check(
        "sequence recorded and read back",
        store.all_sequences()[0]["sequence"] == ("a", "b", "c"),
    )
    store.close()

    store2 = SQLiteLearningStore(root / "learning.db")
    runner.check(
        "restart persistence: experience, record, sequence survive",
        store2.get_experience(exp.id) is not None
        and store2.get_record(record.id) is not None
        and len(store2.all_sequences()) == 1,
    )
    runner.check(
        "lexical lesson search finds the pending lesson",
        any("port" in r.lesson for r in store2.search_lessons("which port do I check first")),
    )
    store2.close()


def section_d(runner: Runner) -> None:
    """D — Pipeline: §13.3 stages over a real §12 engine."""
    runner.section = "D-pipeline"
    memory = MemoryEngine(SQLiteMemoryStore(":memory:"))
    pipeline = LearningPipeline(SQLiteLearningStore(":memory:"), memory=memory)

    # opinion without evidence → refused, but audited
    outcome = pipeline.absorb(
        task_result("t-opinion", outcome="", lesson="tunnels are moody", evidence=[]),
    )
    runner.check(
        "evidence check refuses the opinion (§13.3 stage 3)",
        outcome.lessons_refused == 1
        and outcome.refused[0]["reason"].startswith("no evidence"),
        detail=f"outcome={outcome.to_dict()}",
    )
    runner.check(
        "refused experience still audited, never silently dropped",
        pipeline.stats()["experiences"] >= 1,
    )

    # a real lesson with evidence → stored + promoted
    outcome2 = pipeline.absorb(
        task_result(
            "t-lesson",
            outcome="failure",
            summary="must fix the bearer token before the first call",
            lesson="verify the bearer token before the first tunnel call",
            evidence=[ev(uri="task:t-lesson"), ev(method="test", uri="ci:t-lesson")],
        ),
    )
    runner.check(
        "lesson stored and promoted (two evidence methods ≥ threshold)",
        outcome2.lessons_stored >= 1 and outcome2.lessons_promoted >= 1,
        detail=f"outcome={outcome2.to_dict()}",
    )
    hits = memory.search(MemoryQuery(text="bearer token", types=(MemoryType.LESSON,)))
    runner.check(
        "promotion wrote a §12 record with source=learning + lsig conflict_key",
        any(
            h.record.source == "learning" and (h.record.conflict_key or "").startswith("lsig_")
            for h in hits
        ),
        detail=f"outcome={outcome2.to_dict()}",
    )

    # re-learning merges (occurrences +1, confidence rises, §12 reinforced)
    pipeline.absorb(
        task_result(
            "t-lesson-again",
            outcome="failure",
            summary="again: fix the bearer token before the first call",
            lesson="verify the bearer token before the first tunnel call",
            evidence=[ev(uri="task:t-lesson-again")],
        ),
    )
    records = [
        r
        for r in pipeline._store.list_records()
        if r.lesson == "verify the bearer token before the first tunnel call"
    ]
    runner.check(
        "re-learned lesson MERGES (one record, occurrences 2)",
        len(records) == 1 and records[0].occurrences == 2,
        detail=f"records={[(r.lesson, r.occurrences) for r in records]}",
    )
    runner.check(
        "merged confidence rose with the repeat",
        bool(records)
        and records[0].confidence
        > confidence_for("lesson", evidence_methods=("tool_run", "test"), occurrences=1),
    )
    runner.check(
        "the §12 record was reinforced, not duplicated",
        len(memory.search(MemoryQuery(text="bearer", types=(MemoryType.LESSON,)))) == 1,
    )
    pipeline.close()
    memory.close()


def section_e(runner: Runner) -> None:
    """E — Skills: Task A, Task B, Task C → pattern → candidate."""
    runner.section = "E-skills"
    memory = MemoryEngine(SQLiteMemoryStore(":memory:"))
    pipeline = build_learning_pipeline(":memory:", memory=memory)

    pipeline.absorb(repeat_workflow_task("task-A"))
    pipeline.absorb(repeat_workflow_task("task-B"))
    runner.check(
        "two repeats stay noise — no §13.4 candidate yet",
        len(pipeline._store.list_skills()) == 0,
        detail=f"skills={pipeline._store.list_skills()}",
    )
    outcome = pipeline.absorb(repeat_workflow_task("task-C"))
    skills = pipeline._store.list_skills()
    runner.check(
        "Task A + B + C → ONE skill candidate, occurrences 3",
        len(skills) == 1 and skills[0].occurrences == 3,
        detail=f"skills={[(s.occurrences, s.steps) for s in skills]}",
    )
    runner.check(
        "candidate carries evidence from each lived task",
        {e.uri for e in skills[0].evidence} == {"task:task-A", "task:task-B", "task:task-C"},
    )
    runner.check(
        "the §13.1 skill_candidate experience was minted",
        pipeline._store.count_experiences("skill_candidate") == 1,
    )
    runner.check(
        "candidate promoted into the §12 engine as a SKILL record",
        skills[0].status == "promoted"
        and skills[0].memory_id is not None
        and outcome.skills_promoted >= 1,
        detail=f"skill={skills[0].to_dict() if skills else None}",
    )
    skill_hits = memory.search(MemoryQuery(text="tunnel verified", types=(MemoryType.SKILL,)))
    runner.check(
        "the §12 engine answers with the learned skill",
        any(
            h.record.source == "learning" and "open_tunnel" in h.record.content
            for h in skill_hits
        ),
    )
    pipeline.absorb(repeat_workflow_task("task-D"))
    skills = pipeline._store.list_skills()
    runner.check(
        "a 4th run strengthens the candidate (occurrences 4, still one)",
        len(skills) == 1 and skills[0].occurrences == 4,
    )
    pipeline.close()
    memory.close()


def section_f(runner: Runner) -> None:
    """F — Future retrieval: the §13.3 last arrow, end to end."""
    runner.section = "F-retrieval"
    memory = MemoryEngine(SQLiteMemoryStore(":memory:"))
    pipeline = build_learning_pipeline(":memory:", memory=memory)

    pipeline.absorb(
        task_result(
            "t-src",
            lesson="the Qdrant UUID must be deterministic (UUID5)",
            evidence=[ev(uri="task:t-src"), ev(method="test", uri="ci:t-src")],
        ),
    )
    pipeline.absorb(
        task_result(
            "t-weak",
            lesson="maybe rotate tokens weekly",
            evidence=[ev(uri="task:t-weak")],
        ),
    )
    recall = pipeline.recall("uuid deterministic qdrant", limit=8)
    runner.check(
        "recall surfaces the promoted lesson via the §12 engine",
        any("UUID5" in str(item.get("content", "")) for item in recall.promoted),
        detail=f"promoted={[i.get('content') for i in recall.promoted]}",
    )
    weak_recall = pipeline.recall("tokens rotate weekly", limit=8)
    runner.check(
        "the weak lesson stays pending (below threshold, still visible)",
        any("rotate" in r["lesson"] for r in weak_recall.pending),
        detail=f"pending={weak_recall.pending}",
    )
    runner.check(
        "recall assembles an honest prompt block",
        "Learning context" in weak_recall.as_prompt()
        and "Pending lessons" in weak_recall.as_prompt(),
    )
    # the integration proof: a FUTURE task's §12.7 context already knows
    ctx = memory.retrieve("how do I make qdrant point ids stable")
    text = ctx.as_prompt() if hasattr(ctx, "as_prompt") else str(ctx)
    runner.check(
        "a future task's §12.7 retrieve() already carries the lesson",
        "UUID5" in text or "deterministic" in text.casefold(),
        detail=f"prompt head={text[:200]!r}",
    )
    pipeline.close()
    memory.close()


def section_g(runner: Runner) -> None:
    """G — Restart persistence of the whole pipeline."""
    runner.section = "G-restart"
    root = Path(tempfile.mkdtemp(prefix="nexus-p13-restart-"))
    memory = MemoryEngine(SQLiteMemoryStore(root / "memory.db"))
    pipeline = build_learning_pipeline(root, memory=memory)
    pipeline.absorb(
        task_result(
            "t-live",
            lesson="close the SQLite handle before rmtree (folders lock)",
            evidence=[ev(uri="task:t-live"), ev(method="test", uri="ci:t-live")],
        ),
    )
    pipeline.absorb(repeat_workflow_task("task-A"))
    pipeline.absorb(repeat_workflow_task("task-B"))
    pipeline.close()
    memory.close()

    memory2 = MemoryEngine(SQLiteMemoryStore(root / "memory.db"))
    pipeline2 = build_learning_pipeline(root, memory=memory2)
    stats = pipeline2.stats()
    runner.check(
        "records survive the restart",
        stats["records"] >= 1
        and any("folders lock" in r.lesson for r in pipeline2._store.list_records()),
    )
    runner.check(
        "experiences + sequences survive the restart",
        stats["experiences"] >= 1 and stats["task_sequences"] >= 2,
    )
    # the third task now: the skill candidate must materialize across the restart
    pipeline2.absorb(repeat_workflow_task("task-C"))
    skills = pipeline2._store.list_skills()
    runner.check(
        "the §13.4 pattern fires ACROSS the restart (task C after A, B)",
        len(skills) == 1 and skills[0].occurrences == 3,
        detail=f"skills={[s.occurrences for s in skills]}",
    )
    recall = pipeline2.recall("sqlite folders lock")
    runner.check(
        "recall after restart still finds the lesson (engine re-attached)",
        any("lock" in str(i.get("content", "")) for i in recall.promoted),
    )
    pipeline2.close()
    memory2.close()


def section_h(runner: Runner) -> None:
    """H — Events on a real §2.2 bus."""
    runner.section = "H-events"
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("learning.*", lambda event: seen.append(event.name))
    memory = MemoryEngine(SQLiteMemoryStore(":memory:"))
    pipeline = build_learning_pipeline(":memory:", memory=memory, bus=bus)
    pipeline.absorb(
        task_result(
            "t-bus",
            lesson="events must never break the pipeline",
            evidence=[ev(uri="task:t-bus"), ev(method="test", uri="ci:t-bus")],
        ),
    )
    pipeline.absorb(repeat_workflow_task("bus-A"))
    pipeline.absorb(repeat_workflow_task("bus-B"))
    pipeline.absorb(repeat_workflow_task("bus-C"))
    runner.check(
        "learning.record.created / promoted / skill.found all published",
        "learning.record.created" in seen
        and "learning.record.promoted" in seen
        and "learning.skill.found" in seen,
        detail=f"seen={sorted(set(seen))}",
    )
    runner.check(
        "the pipeline survived the live bus (defensive emit)",
        pipeline.stats()["records"] >= 1,
    )
    pipeline.close()
    memory.close()


def section_i(runner: Runner) -> None:
    """I — Honest degradation without a memory engine."""
    runner.section = "I-degradation"
    pipeline = build_learning_pipeline(":memory:", memory=None)
    outcome = pipeline.absorb(
        task_result(
            "t-nomem",
            lesson="lessons still store without the memory engine",
            evidence=[ev(uri="task:t-nomem"), ev(method="test", uri="ci:t-nomem")],
        ),
    )
    stats = pipeline.stats()
    runner.check(
        "promotion honestly skipped — lesson stays pending",
        outcome.lessons_promoted == 0
        and stats["records_by_status"]["pending"] >= 1
        and stats["records_by_status"]["promoted"] == 0
        and not stats["memory_attached"],
    )
    recall = pipeline.recall("lessons without memory")
    runner.check(
        "recall still answers (pending layer, no engine)",
        any("without the memory engine" in r["lesson"] for r in recall.pending),
    )
    pipeline.close()


def section_j(runner: Runner) -> None:
    """J — Learning ≠ memory: dedupe and the untouched §12.8 ladder."""
    runner.section = "J-semantics"
    memory = MemoryEngine(SQLiteMemoryStore(":memory:"))
    pipeline = build_learning_pipeline(":memory:", memory=memory)
    for tid in ("j1", "j2", "j3"):
        pipeline.absorb(
            task_result(
                tid,
                lesson="the same lesson learned thrice is one record",
                evidence=[ev(uri=f"task:{tid}")],
            ),
        )
    records = [r for r in pipeline._store.list_records() if "thrice" in r.lesson]
    runner.check(
        "dedupe: three absorptions → ONE record, occurrences 3",
        len(records) == 1 and records[0].occurrences == 3,
    )
    # the operator's *now* outranks an old lesson (§12.8 untouched)
    memory.remember(
        "use tokens from the vault only",
        type=MemoryType.RULE,
        scope=MemoryScope.USER,
        source="user",
        conflict_key="tokens",
    )
    pipeline.absorb(
        task_result(
            "j-l1",
            lesson="copy tokens into the repo for convenience",
            evidence=[ev(uri="task:j-l1"), ev(method="test", uri="ci:j-l1")],
        ),
    )
    ctx = memory.retrieve("how should I handle tokens")
    text = ctx.as_prompt() if hasattr(ctx, "as_prompt") else str(ctx)
    user_pos = text.casefold().find("vault")
    lesson_pos = text.casefold().find("repo for convenience")
    runner.check(
        "the §12.8 ladder stays in force: the USER rule outranks the learned lesson",
        user_pos != -1 and (lesson_pos == -1 or user_pos < lesson_pos),
        detail=f"vault@{user_pos} lesson@{lesson_pos}",
    )
    pipeline.close()
    memory.close()


def section_k(runner: Runner, *, regression: bool = True) -> None:
    """K — Integration + regression."""
    runner.section = "K-integration"
    import nexus

    runner.check(
        "NEXUS_PHASE >= 13 (learning shipped; later phases may extend)",
        isinstance(getattr(nexus, "NEXUS_PHASE", None), int)
        and nexus.NEXUS_PHASE >= 13,
        detail=f"got {getattr(nexus, 'NEXUS_PHASE', None)!r}",
    )
    runner.check(
        "__version__ >= 0.13.0",
        str(getattr(nexus, "__version__", "")).startswith("0.13")
        or str(getattr(nexus, "__version__", "")) > "0.13.0",
        detail=f"got {getattr(nexus, '__version__', '')!r}",
    )
    import importlib.util

    shipped = all(
        importlib.util.find_spec(f"nexus.learning.{mod}") is not None
        for mod in ("contracts", "extractor", "store", "pipeline", "skills")
    )
    runner.check("all five learning modules importable", shipped)
    import tomllib

    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    runner.check(
        "core dependencies stay empty (Plan §2 — learning adds none)",
        data["project"]["dependencies"] == [],
    )
    runner.check(
        "version bumped to 0.13.0",
        data["project"]["version"] == "0.13.0",
        detail=f"got {data['project']['version']!r}",
    )
    if regression:
        _regression(runner)


def _regression(runner: Runner) -> None:
    """Phases 1–12 harnesses stay green (subprocess, house pattern)."""
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
        ("phase12", "Phase 12"),
    ]
    for phase_dir, label in prior:
        argv = [
            sys.executable,
            str(REPO_ROOT / "tests" / phase_dir / "verify_exit_criteria.py"),
        ]
        if phase_dir == "phase12":
            argv.append("--no-regression")  # it has its own 1–11 chain
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=2400)
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
    parser.add_argument(
        "--no-regression",
        action="store_true",
        help="skip the Phase 1–12 subprocess regression (local quick runs)",
    )
    args = parser.parse_args()
    print("PHASE 13 — Learning System (New Plan §13) exit criteria")
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
