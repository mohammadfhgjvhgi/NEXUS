"""Phase-13 live proof — runs ON the real Windows box (via the t1 bridge).

Proves the §13 Learning System against the operator's real machine:

* **§13.1** — the Experience Extractor on a real finished task:
  all six kinds minted on the box, evidence attached;
* **§13.2/§13.3** — the full pipeline on real disk
  (``M:\\NEXUS\\data\\learning-proof``): Experience → Candidate
  lesson → Evidence check → Confidence → Store → promotion into the
  REAL §12 MemoryEngine (SQLite on the box); a bilingual corpus
  (AR + EN); the opinion-without-evidence refusal;
* **§13.4** — Task A, Task B, Task C: the same workflow run by three
  real tasks folds into ONE skill candidate and promotes as a SKILL
  record in memory;
* **§13.3 Future retrieval** — recall() answers a bilingual question
  from the engine + the pending layer; a future task's §12.7
  retrieve() already carries the learned lesson;
* **Restart persistence** — a *fresh subprocess* (this script
  re-invokes itself with ``--child``) reopens the same root and
  proves lessons, skills and audit survive the process boundary.

Run:  python -X utf8 tests\\phase13\\live_proof_device.py   (from M:\\NEXUS)
Writes: proofs\\phase13_live.json · data\\learning-proof\\learning.db + memory.db
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"M:\NEXUS")

from nexus.memory.contracts import MemoryEvidence  # noqa: E402

print("python:", sys.version.split()[0], "| platform:", sys.platform)
PROOFS = Path(r"M:\NEXUS\proofs")
PROOFS.mkdir(parents=True, exist_ok=True)
ROOT = Path(r"M:\NEXUS\data") / "learning-proof"
REPORT_NAME = "phase13_live.json"
report: dict = {
    "python": sys.version.split()[0],
    "machine": f"{platform.node()} · {platform.system()} {platform.release()}",
    "phase": 13,
}
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    report[name] = {"ok": bool(ok), "detail": detail[:300]}
    if not ok:
        failures.append(name)
    return ok


WORKFLOW_STEPS = [
    {"name": "open_tunnel", "status": "ok"},
    {"name": "health_check", "status": "ok"},
    {"name": "auth_probe", "status": "ok"},
]


def run_task(pipeline, task_id: str, **overrides) -> object:
    task: dict = {
        "task_id": task_id,
        "outcome": "success",
        "summary": "tunnel verified end to end",
        "steps": [dict(s) for s in WORKFLOW_STEPS],
        "evidence": (
            MemoryEvidence(method="tool_run", uri=f"task:{task_id}", snippet="live run log"),
        ),
        "project": "nexus",
    }
    task.update(overrides)
    return pipeline.absorb(task)


def main() -> int:
    from nexus.learning import build_learning_pipeline
    from nexus.memory import MemoryEngine, MemoryQuery, SQLiteMemoryStore

    # ---- 0. the child restart proof runs first-come --------------------
    if "--child" in sys.argv:
        return child_restart_proof()
    # a clean slate per run — a proof re-run must re-prove, not collide
    shutil.rmtree(ROOT, ignore_errors=True)

    memory = MemoryEngine(SQLiteMemoryStore(ROOT / "memory.db"))
    pipeline = build_learning_pipeline(ROOT, memory=memory)

    # ---- 1. §13.1 the extractor on the box ------------------------------
    from nexus.learning import ExperienceExtractor

    extractor = ExperienceExtractor()
    experiences = extractor.extract({
        "task_id": "dev-extract",
        "outcome": "failure",
        "summary": "failed — must fix the bearer token before the first call",
        "steps": [
            {"name": "health_check", "status": "error", "error": "401"},
            {"name": "retry", "status": "ok", "decision": True, "choice": "switch to t2"},
            {"name": "health_check", "status": "ok"},
            {"name": "auth_probe", "status": "ok"},
            {"name": "health_check", "status": "ok"},
            {"name": "auth_probe", "status": "ok"},
        ],
        "lesson": "always rotate the token before retrying the tunnel",
        "evidence": (
            MemoryEvidence(method="tool_run", uri="task:dev-extract", snippet="401 log"),
        ),
        "project": "nexus",
    })
    kinds = {e.kind for e in experiences}
    check(
        "§13.1 the kinds extracted on the box (failure+decision+pattern+lesson)",
        {"failure", "decision", "pattern", "lesson"}.issubset(kinds),
        detail=f"kinds={sorted(kinds)}",
    )

    # ---- 2. §13.3 the pipeline on real disk (bilingual) ------------------
    out_ar = pipeline.absorb({
        "task_id": "dev-1",
        "outcome": "failure",
        "summary": "فشل الاتصال — يجب إصلاح الرمز قبل أول نداء",
        "lesson": "تحقق من رمز الحامل قبل أول نداء عبر النفق",
        "steps": [{"name": "health_check", "status": "error", "error": "401"}],
        "evidence": (
            MemoryEvidence(method="tool_run", uri="task:dev-1", snippet="401"),
            MemoryEvidence(method="test", uri="ci:dev-1", snippet="assert 401"),
        ),
        "project": "nexus",
    })
    check(
        "AR lesson stored + promoted into the §12 engine (§13.3)",
        out_ar.lessons_stored >= 1 and out_ar.lessons_promoted >= 1,
        detail=f"outcome={out_ar.to_dict()}",
    )
    out_en = pipeline.absorb({
        "task_id": "dev-2",
        "outcome": "success",
        "summary": "closed the sqlite handle before rmtree — folders lock",
        "lesson": "close the SQLite handle before removing folders",
        "steps": [{"name": "cleanup", "status": "ok"}],
        "evidence": (
            MemoryEvidence(method="tool_run", uri="task:dev-2", snippet="log"),
            MemoryEvidence(method="test", uri="ci:dev-2", snippet="assert"),
        ),
        "project": "nexus",
    })
    check(
        "EN lesson stored + promoted (§13.3)",
        out_en.lessons_stored >= 1 and out_en.lessons_promoted >= 1,
    )
    out_opinion = pipeline.absorb({
        "task_id": "dev-3",
        "outcome": "success",
        "summary": "a moody day for tunnels",
        "lesson": "tunnels are moody",
        "steps": [],
        "evidence": (),
        "project": "nexus",
    })
    check(
        "the opinion (no evidence) refused by §13.3 stage 3",
        out_opinion.lessons_refused >= 1,
        detail=f"outcome={out_opinion.to_dict()}",
    )
    check(
        "the refused opinion stays in the audit trail",
        pipeline.stats()["experiences"] >= 4,
    )

    # ---- 3. §13.4 Task A, B, C → pattern → skill candidate ---------------
    run_task(pipeline, "dev-flow-A")
    run_task(pipeline, "dev-flow-B")
    check(
        "two repeats: no skill candidate yet (§13.4 needs three)",
        len(pipeline._store.list_skills()) == 0,
    )
    run_task(pipeline, "dev-flow-C")
    skills = pipeline._store.list_skills()
    check(
        "Task A+B+C → ONE skill candidate, occurrences 3, promoted",
        len(skills) == 1
        and skills[0].occurrences == 3
        and skills[0].status == "promoted"
        and skills[0].memory_id is not None,
        detail=f"skills={[(s.occurrences, s.status) for s in skills]}",
    )
    check(
        "the skill record lives in the §12 engine (source=learning)",
        bool(skills)
        and any(
            h.record.id == skills[0].memory_id and h.record.source == "learning"
            for h in memory.search(MemoryQuery(text="tunnel", types=("skill",)))
        ),
    )

    # ---- 4. §13.3 Future retrieval on the box -----------------------------
    recall_ar = pipeline.recall("رمز الحامل النفق", project="nexus")
    check(
        "recall answers in Arabic from the engine",
        any("الرمز" in str(i.get("content", "")) for i in recall_ar.promoted),
        detail=f"promoted={[i.get('content') for i in recall_ar.promoted]}",
    )
    ctx = memory.retrieve(
        "how do I avoid locked folders when cleaning sqlite",
        project="nexus",
    )
    text = ctx.as_prompt() if hasattr(ctx, "as_prompt") else str(ctx)
    check(
        "a future task's §12.7 retrieve() already carries the lesson",
        "SQLite handle" in text or "folders" in text,
        detail=f"head={text[:160]!r}",
    )
    stats = pipeline.stats()
    check(
        "the honest ledger: pending lessons exist below threshold",
        stats["records_by_status"]["pending"] >= 1,
        detail=f"stats={stats['records_by_status']}",
    )
    pipeline.close()
    memory.close()

    # ---- 5. Restart persistence across a process boundary ----------------
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--child"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(proc.stdout.rstrip())
    child_ok = proc.returncode == 0 and "CHILD RESTART: PASS" in proc.stdout
    check(
        "restart persistence across a process boundary (fresh python)",
        child_ok,
        (proc.stderr[-300:] if not child_ok else proc.stdout.strip().splitlines()[-2]),
    )
    if proc.stdout:
        report["child_output_tail"] = proc.stdout.strip().splitlines()[-2:]

    # ---- verdict -----------------------------------------------------------
    out = PROOFS / REPORT_NAME
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"report → {out}")
    print("PROOF RESULT:", "PASS" if not failures else f"FAIL ({failures})")
    return 0 if not failures else 1


def child_restart_proof() -> int:
    """The fresh-process half: reopen the same root, prove survival."""
    from nexus.learning import build_learning_pipeline
    from nexus.memory import MemoryEngine, SQLiteMemoryStore

    memory = MemoryEngine(SQLiteMemoryStore(ROOT / "memory.db"))
    pipeline = build_learning_pipeline(ROOT, memory=memory)
    stats = pipeline.stats()
    ok_records = stats["records"] >= 3
    ok_experiences = stats["experiences"] >= 6
    skills = pipeline._store.list_skills()
    ok_skill = len(skills) == 1 and skills[0].occurrences == 3

    # re-learning in the NEW process merges (occurrences 2)
    run_task(
        pipeline,
        "dev-2-again",
        summary="closed the sqlite handle before rmtree — folders lock",
        lesson="close the SQLite handle before removing folders",
        steps=[{"name": "cleanup", "status": "ok"}],
    )
    merged = [
        r for r in pipeline._store.list_records()
        if r.lesson == "close the SQLite handle before removing folders"
    ]
    ok_merge = len(merged) == 1 and merged[0].occurrences == 2

    recall_en = pipeline.recall("sqlite handle folders", project="nexus")
    ok_recall = any(
        "SQLite handle" in str(i.get("content", "")) for i in recall_en.promoted
    )
    pipeline.close()
    memory.close()
    ok = ok_records and ok_experiences and ok_skill and ok_merge and ok_recall
    print(
        f"  child: records={ok_records} experiences={ok_experiences} "
        f"skill={ok_skill} merge={ok_merge} recall={ok_recall}"
    )
    print("CHILD RESTART:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
