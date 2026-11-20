#!/usr/bin/env python3
"""Phase-12 live memory proof — runs on a REAL Qdrant engine (CI + device).

One end-to-end §12.5/§12.7 roundtrip on whatever this runtime really has:

* **embed**   — HashingEmbedder vectors (deterministic, AR+EN content);
* **engine**  — ``build_memory_engine(root, vector_backend="auto")`` with
  qdrant-client installed → the Qdrant local-mode persisted store must be
  the auto pick (``backend_report`` says so — no silent local fallback);
* **write**   — remember() a bilingual corpus across §12.2 scopes;
* **search**  — semantic retrieval ranks the right records (AR + EN);
* **filter**  — filtered retrieval respects the container payloads;
* **conflict**— the §12.8 ladder resolves a real conflict family;
* **forget**  — a §12.9 tombstone removes the vector from Qdrant;
* **restart** — close(), new engine on the same root, the memories
  survive (SQLite + Qdrant local persistence, one path each).

Fail-fast: qdrant-client missing → exit 1 with the honest probe string
(this job exists to prove the REAL engine, not to skip it).

Run:  python tests/phase12/live_memory_ci.py
Exit 0 only when the whole chain passes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.memory import (  # noqa: E402
    MemoryQuery,
    MemoryScope,
    MemoryType,
    build_memory_engine,
    qdrant_probe,
)


def main() -> int:
    probe = qdrant_probe()
    if probe is not None:
        print(json.dumps({"error": "qdrant-client unavailable", "probe": probe}))
        print("PROOF RESULT: FAIL (qdrant-client must be installed for this proof)")
        return 1

    checks: list[tuple[str, bool]] = []
    root = Path(tempfile.mkdtemp(prefix="nexus-p12-live-"))

    # ---- 1. the factory picks the real engine -------------------------
    engine = build_memory_engine(root, vector_backend="auto")
    backend = engine.backend()
    checks.append((
        "auto backend is Qdrant (local persisted mode)",
        backend["vector_backend"] == "qdrant-local"
        and "qdrant" in backend["report"].casefold(),
    ))
    print(f"  backend: {backend['vector_backend']} — {backend['report']}")

    # ---- 2. bilingual corpus across scopes ----------------------------
    r_decision = engine.remember(
        "قررنا استخدام llama.cpp كمحرّك الاستدلال الرئيسي",
        type=MemoryType.DECISION,
        scope=MemoryScope.PROJECT,
        project="nexus",
        conflict_key="engine",
    )
    r_pref = engine.remember(
        "old lesson: use ONNX runtime for inference",
        type=MemoryType.LESSON,
        scope=MemoryScope.LESSON,
        conflict_key="engine",
    )
    r_task = engine.remember(
        "task fact: the tunnel port is 8452",
        type=MemoryType.FACT,
        scope=MemoryScope.TASK,
        task="task-live",
    )
    r_global = engine.remember(
        "global law: never fabricate verification evidence",
        type=MemoryType.RULE,
        scope=MemoryScope.GLOBAL,
    )
    checks.append((
        "four §12.2 scopes written (project/lesson/task/global)",
        engine.backend()["records"] == 4 and engine.backend()["vectors"] == 4,
    ))

    # ---- 3. semantic search ranks the right records -------------------
    hits_ar = engine.search(
        MemoryQuery(text="محرّك الاستدلال llama", project="nexus")
    )
    checks.append((
        "semantic retrieval finds the Arabic decision",
        any(h.record.id == r_decision.id for h in hits_ar[:2]),
    ))
    hits_en = engine.search(
        MemoryQuery(text="llama.cpp engine choice", project="nexus")
    )
    checks.append((
        "semantic retrieval finds it from English too",
        any(h.record.id == r_decision.id for h in hits_en[:3]),
    ))
    ctx = engine.retrieve("port number for the tunnel", task="task-live")
    checks.append((
        "retrieve() assembles the task-scoped context",
        any("8452" in b.text for b in ctx.blocks),
    ))
    conflict_ctx = engine.retrieve(
        "engine choice llama ONNX", project="nexus"
    )
    conflict_joined = conflict_ctx.as_prompt()
    checks.append((
        "the §12.8 ladder kept the decision, dropped the ONNX lesson",
        "llama.cpp" in conflict_joined and "ONNX" not in conflict_joined,
    ))
    checks.append((
        "the conflict is documented in the context",
        any("engine" in line for line in conflict_ctx.conflicts),
    ))

    # ---- 4. filtered retrieval (§12.5) --------------------------------
    flt_hits = engine.search(
        MemoryQuery(text="ONNX lesson", scope=MemoryScope.LESSON)
    )
    checks.append((
        "scope-filtered search returns only the lesson",
        [h.record.id for h in flt_hits] == [r_pref.id],
    ))

    # ---- 5. forget removes the vector from Qdrant ---------------------
    result = engine.forget(record_id=r_pref.id, reason="live proof")
    checks.append((
        "§12.9 forget drops the Qdrant point",
        result.audit_rows == 1 and engine.backend()["vectors"] == 3,
    ))

    # ---- 6. restart persistence ---------------------------------------
    engine.close()
    engine2 = build_memory_engine(root, vector_backend="auto")
    hits2 = engine2.search(
        MemoryQuery(text="tunnel port", task="task-live")
    )
    checks.append((
        "restart persistence: the port fact survives in Qdrant",
        any(h.record.id == r_task.id for h in hits2[:2]),
    ))
    ctx2 = engine2.retrieve("global law evidence")
    checks.append((
        "restart persistence: the global rule survives in SQLite",
        any(r_global.id == b.record_id for b in ctx2.blocks)
        or "fabricate" in ctx2.as_prompt(),
    ))
    engine2.close()

    failed = [label for label, ok in checks if not ok]
    print()
    print(json.dumps({
        "checks": len(checks),
        "failed": failed,
        "backend": backend["vector_backend"],
        "embedder": backend["embedder"],
        "dimension": backend["dimension"],
        "root": str(root),
    }, ensure_ascii=False))
    print("PROOF RESULT:", "PASS" if not failed else f"FAIL ({failed})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
