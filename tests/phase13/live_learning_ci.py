#!/usr/bin/env python3
"""Phase-13 live learning proof — real files, real child process.

One end-to-end §13.3 roundtrip on whatever this runtime really has —
no fakes, no mocks:

* **absorb**  — three finished tasks (bilingual AR + EN lessons with
                real evidence) flow through the full pipeline: extract
                → candidate lesson → evidence check → confidence →
                store → promotion into a REAL §12 MemoryEngine (SQLite
                file, local vectors).
* **skill**    — the §13.4 corpus: the same workflow run by three
                different tasks folds into ONE skill candidate and
                promotes as a SKILL record.
* **restart**  — a CHILD PROCESS (fresh interpreter) re-opens the same
                root: records, experiences, sequences and skills must
                survive; the next absorb still merges (occurrences 2).
* **recall**   — the child process answers a bilingual recall: the
                promoted lessons arrive from the §12 engine, the weak
                one stays pending, the skill is searchable.

Fail-fast: anything missing → exit 1 with the honest reason.

Run:  python tests/phase13/live_learning_ci.py
Exit 0 only when the whole chain passes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.learning import build_learning_pipeline  # noqa: E402
from nexus.memory import MemoryEngine, SQLiteMemoryStore  # noqa: E402
from nexus.memory.contracts import MemoryEvidence  # noqa: E402

WORKFLOW_STEPS = [
    {"name": "open_tunnel", "status": "ok"},
    {"name": "health_check", "status": "ok"},
    {"name": "auth_probe", "status": "ok"},
]


def ev(uri: str, method: str = "tool_run") -> MemoryEvidence:
    return MemoryEvidence(method=method, uri=uri, snippet="live run log")


def phase_parent(root: Path) -> int:
    checks: list[tuple[str, bool]] = []

    memory = MemoryEngine(SQLiteMemoryStore(root / "memory.db"))
    pipeline = build_learning_pipeline(root, memory=memory)

    # ---- 1. bilingual lessons, full §13.3 flow -------------------------
    out_ar = pipeline.absorb({
        "task_id": "live-1",
        "outcome": "failure",
        "summary": "فشل الاتصال — يجب إصلاح الرمز قبل أول نداء",
        "lesson": "تحقق من رمز الحامل قبل أول نداء عبر النفق",
        "steps": [{"name": "health_check", "status": "error", "error": "401"}],
        "evidence": [ev("task:live-1"), ev("ci:live-1", method="test")],
        "project": "nexus",
    })
    checks.append((
        "AR lesson absorbed (stored+promoted)",
        out_ar.lessons_stored >= 1 and out_ar.lessons_promoted >= 1,
    ))
    out_en = pipeline.absorb({
        "task_id": "live-2",
        "outcome": "success",
        "summary": "closed the sqlite handle before rmtree — folders lock",
        "lesson": "close the SQLite handle before removing folders",
        "steps": [{"name": "cleanup", "status": "ok"}],
        "evidence": [ev("task:live-2"), ev("ci:live-2", method="test")],
        "project": "nexus",
    })
    checks.append((
        "EN lesson absorbed (stored+promoted)",
        out_en.lessons_stored >= 1 and out_en.lessons_promoted >= 1,
    ))
    pipeline.absorb({
        "task_id": "live-3",
        "outcome": "success",
        "summary": "tokens maybe rotate weekly",
        "lesson": "maybe rotate tokens weekly",
        "steps": [{"name": "rotate", "status": "ok"}],
        "evidence": [ev("task:live-3")],
        "project": "nexus",
    })
    checks.append((
        "weak lesson stays pending (single evidence, below threshold)",
        any(
            r.status == "pending" and r.occurrences == 1
            for r in pipeline._store.list_records()
            if r.lesson == "maybe rotate tokens weekly"
        ),
    ))

    # ---- 2. the §13.4 skill corpus (2 of 3 here; the 3rd in the child) --
    pipeline.absorb({
        "task_id": "flow-A",
        "outcome": "success",
        "summary": "tunnel verified end to end",
        "steps": [dict(s) for s in WORKFLOW_STEPS],
        "evidence": [ev("task:flow-A")],
        "project": "nexus",
    })
    pipeline.absorb({
        "task_id": "flow-B",
        "outcome": "success",
        "summary": "tunnel verified end to end",
        "steps": [dict(s) for s in WORKFLOW_STEPS],
        "evidence": [ev("task:flow-B")],
        "project": "nexus",
    })
    checks.append((
        "two repeats: no skill candidate yet (§13.4 needs three)",
        len(pipeline._store.list_skills()) == 0,
    ))
    stats = pipeline.stats()
    checks.append((
        "promotion wrote real §12 records (source=learning)",
        len([
            r for r in pipeline._store.list_records() if r.memory_id
        ]) >= 2
        and stats["records"] >= 3,
    ))
    pipeline.close()
    memory.close()

    # ---- 3. CHILD PROCESS restart: same root, fresh interpreter --------
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--phase",
            "child",
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(proc.stdout.rstrip())
    child_verdict = {}
    child_line = ""
    for line in proc.stdout.strip().splitlines():
        if line.startswith("CHILD-VERDICT "):
            child_line = line
            child_verdict = json.loads(line[len("CHILD-VERDICT "):])
    checks.append((
        f"child process restart: exit 0 (err tail: {proc.stderr[-200:]!r})",
        proc.returncode == 0,
    ))
    for key in (
        "records_survive",
        "experiences_survive",
        "third_flow_folds_skill",
        "merge_occurrences_2",
        "recall_ar",
        "recall_en",
        "recall_pending",
        "skill_in_memory",
    ):
        checks.append((f"child: {key}", bool(child_verdict.get(key))))
    if not child_line:
        print("  child produced no verdict line — failing")
        checks.append(("child verdict line present", False))

    failed = [label for label, *_rest in checks if not _rest[0]]
    print()
    print(json.dumps({
        "checks": len(checks),
        "failed": failed,
        "root": str(root),
    }, ensure_ascii=False))
    print("PROOF RESULT:", "PASS" if not failed else f"FAIL ({failed})")
    return 0 if not failed else 1


def phase_child(root: Path) -> int:
    """The restart leg — a fresh interpreter over the same files."""
    memory = MemoryEngine(SQLiteMemoryStore(root / "memory.db"))
    pipeline = build_learning_pipeline(root, memory=memory)
    verdict: dict[str, bool] = {}

    stats = pipeline.stats()
    verdict["records_survive"] = stats["records"] >= 3
    verdict["experiences_survive"] = stats["experiences"] >= 6
    verdict["sequences_survive"] = stats["task_sequences"] >= 4

    # the third workflow run — the §13.4 fold must fire across the restart
    pipeline.absorb({
        "task_id": "flow-C",
        "outcome": "success",
        "summary": "tunnel verified end to end",
        "steps": [dict(s) for s in WORKFLOW_STEPS],
        "evidence": [ev("task:flow-C")],
        "project": "nexus",
    })
    skills = pipeline._store.list_skills()
    verdict["third_flow_folds_skill"] = (
        len(skills) == 1 and skills[0].occurrences == 3
    )
    verdict["skill_in_memory"] = bool(skills) and skills[0].memory_id is not None

    # re-learning an old lesson in the NEW process → merge, not duplicate
    pipeline.absorb({
        "task_id": "live-2-again",
        "outcome": "success",
        "summary": "closed the sqlite handle before rmtree — folders lock",
        "lesson": "close the SQLite handle before removing folders",
        "steps": [{"name": "cleanup", "status": "ok"}],
        "evidence": [ev("task:live-2-again")],
        "project": "nexus",
    })
    merged = [
        r for r in pipeline._store.list_records()
        if "SQLite handle" in r.lesson
    ]
    verdict["merge_occurrences_2"] = (
        len(merged) == 1 and merged[0].occurrences == 2
    )

    recall_ar = pipeline.recall("رمز الحامل النفق", project="nexus", limit=8)
    verdict["recall_ar"] = any(
        "الرمز" in str(i.get("content", "")) for i in recall_ar.promoted
    )
    recall_en = pipeline.recall("sqlite handle folders lock", project="nexus", limit=8)
    verdict["recall_en"] = any(
        "SQLite handle" in str(i.get("content", "")) for i in recall_en.promoted
    )
    weak_recall = pipeline.recall("tokens rotate weekly", project="nexus", limit=8)
    verdict["recall_pending"] = any(
        "rotate" in r["lesson"] for r in weak_recall.pending
    )
    pipeline.close()
    memory.close()
    print("CHILD-VERDICT " + json.dumps(verdict, ensure_ascii=False))
    return 0 if all(verdict.values()) else 1


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="nexus-p13-live-"))
    args = sys.argv[1:]
    if len(args) >= 4 and args[0] == "--phase" and args[1] == "child":
        return phase_child(Path(args[3]))
    print(f"parent phase — root: {root}")
    return phase_parent(root)


if __name__ == "__main__":
    sys.exit(main())
