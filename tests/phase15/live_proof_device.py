#!/usr/bin/env python3
"""Phase-15 device live proof — runs ON the real Windows box.

The §15 exit gate on the operator's machine — the box is the judge:

* **part a** (fast, ~25s) — the five behavior checks:
  * **specialists** — the ten §15.2 roles register into a real temp
                     AgentRegistry and answer discovery.
  * **loop-green** — a real temp project with a real bug: the §15.6
                     loop Understand→Plan→Edit→Build→Test→Debug→
                     Retest→Review approves after one debug cycle, and
                     main.py is FIXED ON DISK.
  * **events**      — only canonical §2.2 events on the wire.
  * **loop-bounded** — the unfixable path: rejected exactly at the
                     bound, skeleton eight-wide, never an infinite spin.
  * **session**     — the Cline-inspired trail persists and revives.

* **part b** (self, ~30s) — the CodingAgent ANALYZES M:\\NEXUS itself:
  the developer agent reads its own codebase through the §14 engine
  (analyze → files + symbols).

The two parts exist because the tunnel's danger-1 ``code_run_tests``
gatekeeper caps a single run at 60s: the bridge calls them as two
pytest nodes (``::test_part_a_fast_checks`` / ``::test_part_b_self_analysis``)
and both share one verdict file — part a writes the five checks and
marks ``__part_b__`` pending; part b merges the self-analysis in and
clears the marker. ``--part all`` (the default) keeps the classic
single-shot behaviour for local runs.

Writes the verdict to ``M:\\NEXUS\\proofs\\phase15_live.json``.
Exit 0 only when every check in the executed part passes.

Run:  python -X utf8 tests\\phase15\\live_proof_device.py [--part a|b|all]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import cast  # noqa: E402

from coding_project import (  # noqa: E402
    BAD_FIX,
    GOOD_FIX,
    MAIN_FIXED,
    make_buggy_project,
)

from nexus import NEXUS_PHASE, __version__  # noqa: E402
from nexus.agents.registry import AgentRegistry  # noqa: E402
from nexus.coding import (  # noqa: E402
    LOOP_STAGE_ORDER,
    SPECIALIST_ROLES,
    CodingAgent,
    CodingLoop,
    CodingOperationKind,
    CodingSession,
    OperationRequest,
)
from nexus.coding.specialists import register_coding_specialists  # noqa: E402
from nexus.events import CANONICAL_EVENTS  # noqa: E402

VERDICT_PATH = Path(r"M:\NEXUS\proofs\phase15_live.json")
PENDING_KEY = "__part_b__"

CHECKS: dict[str, dict[str, object]] = {}


def record(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS[name] = {"ok": bool(ok), "detail": detail}
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if not ok else ""))
    return ok


def run_part_a() -> None:
    """The five fast behavior checks (~25s)."""
    tmp = Path(tempfile.mkdtemp(prefix="nexus_p15_dev_"))

    # ---------------------------------------------------------- specialists
    registry = AgentRegistry(tmp / "agents")
    agents = register_coding_specialists(registry)
    roles = {a.role for a in registry.discover_agents()}
    record(
        "ten specialists register + answer discovery",
        len(agents) == 10 and roles == set(SPECIALIST_ROLES),
        f"roles={sorted(roles)}",
    )

    # ------------------------------------------------------------ loop green
    project = make_buggy_project(tmp / "workspace")
    agent = CodingAgent(project)
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    order = tuple(stage.value for stage in LOOP_STAGE_ORDER)
    fixed_on_disk = (project / "main.py").read_text(encoding="utf-8") == MAIN_FIXED
    record(
        "the §15.6 loop fixes a real bug on disk (approved, 8 stages)",
        result.approved
        and result.stage_order == order
        and result.debug_cycles == 1
        and fixed_on_disk,
        f"approved={result.approved} cycles={result.debug_cycles} "
        f"order={result.stage_order} fixed={fixed_on_disk}",
    )
    record(
        "only canonical events on the wire",
        set(result.events) <= CANONICAL_EVENTS,
        f"non-canonical={set(result.events) - CANONICAL_EVENTS}",
    )

    # --------------------------------------------------------- loop bounded
    unfix_dir = make_buggy_project(tmp / "unfixable")
    unfix_agent = CodingAgent(unfix_dir)
    unfix = CodingLoop(unfix_agent, unfix_dir, "fix the divide function", 2, fixes=[BAD_FIX]).run()
    record(
        "unfixable: bounded rejection exactly at the bound",
        unfix.approved is False
        and unfix.debug_cycles == 2
        and unfix.stage_order[:8] == order
        and unfix.stage_order[8:] == ("debug", "retest"),
        f"cycles={unfix.debug_cycles} order={unfix.stage_order}",
    )

    # --------------------------------------------------------------- session
    sess_project = make_buggy_project(tmp / "session_ws")
    session = CodingSession(goal="device proof", directory=sess_project / "sessions")
    sess_agent = CodingAgent(sess_project, session=session)
    sess_result = CodingLoop(
        sess_agent, sess_project, "fix the divide function", 3, fixes=[GOOD_FIX]
    ).run()
    trail_ok = (
        sess_result.approved
        and session.path is not None
        and session.path.exists()
        and "main.py" in session.record.files_edited
    )
    revived_ok = False
    if trail_ok and session.path is not None:
        revived = CodingSession.load(session.path)
        revived_ok = (
            revived.session_id == session.session_id
            and revived.files_edited == session.record.files_edited
        )
    record(
        "Cline-style session trail persists + revives",
        trail_ok and revived_ok,
        f"trail={trail_ok} revived={revived_ok}",
    )


def run_part_b() -> None:
    """The self-analysis check (~30s) — NEXUS reads its own codebase."""
    nexus_root = Path(r"M:\NEXUS")
    if nexus_root.exists():
        self_agent = CodingAgent(nexus_root)
        analysis = self_agent.execute(
            OperationRequest(
                kind=cast(CodingOperationKind, "analyze"),  # runtime coerces
                goal="NEXUS reads its own codebase",
            )
        )
        payload = analysis.payload
        files = int(payload.get("files_indexed", 0))
        symbols = int(payload.get("symbols", 0))
        record(
            "the developer agent analyzes M:\\NEXUS itself",
            files >= 200 and symbols >= 400,
            f"files={files} symbols={symbols}",
        )
    else:
        record("the developer agent analyzes M:\\NEXUS itself", False, "root missing")


def write_verdict(part: str) -> None:
    """Merge semantics: part b folds into part a's pending verdict.

    The verdict file belongs to the real Windows box: on any host where
    ``M:\\`` is not a real drive, ``Path(r"M:\\...")`` is a *relative*
    path and writing it would litter the repo with a file literally
    named ``M:\\NEXUS\\proofs\\...`` — refuse instead (anchor check).
    """
    if not VERDICT_PATH.anchor or not Path(VERDICT_PATH.anchor).exists():
        print("  [WARN] verdict not written — M:\\ is not a real drive on this host")
        return
    merged: dict[str, object] = dict(CHECKS)
    if part == "b":
        try:
            existing = json.loads(VERDICT_PATH.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                # part a's checks first, then part b's (order-stable)
                merged = {k: v for k, v in existing.items() if k != PENDING_KEY}
                merged.update(CHECKS)
        except (OSError, json.JSONDecodeError):
            pass
    if part == "a":
        merged[PENDING_KEY] = "pending"
    try:
        VERDICT_PATH.parent.mkdir(parents=True, exist_ok=True)
        VERDICT_PATH.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        print(f"  [WARN] verdict not written: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-15 device live proof")
    parser.add_argument("--part", choices=("all", "a", "b"), default="all")
    args = parser.parse_args()

    print("PHASE 15 — Coding System · device live proof (the box is the judge)")
    print(f"  python {platform.python_version()} · nexus-core {__version__} · phase {NEXUS_PHASE}")
    print(f"  part: {args.part}")
    print()

    if args.part in ("all", "a"):
        run_part_a()
    if args.part in ("all", "b"):
        run_part_b()

    write_verdict(args.part)

    print()
    print("=" * 72)
    failures = sum(1 for c in CHECKS.values() if not c.get("ok"))
    total = len(CHECKS)
    if failures:
        print(f"live_proof_device.py ({args.part}) — {total - failures}/{total} checks, {failures} FAILED")
        print("=" * 72)
        return 1
    print(f"live_proof_device.py ({args.part}) — {total}/{total} checks, 0 failed")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
