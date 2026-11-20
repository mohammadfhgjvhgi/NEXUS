#!/usr/bin/env python3
"""Phase 15 verification harness — New Plan §15 Exit Gate.

Proves the Coding System section by section:

* A — Contracts (§15.1/§15.2/§15.6): the seven operations, the ten
       specialists, the eight loop stages — all verbatim; request and
       result shapes refuse misuse honestly.
* B — Specialist Agents (§15.2): all ten register into the §6.4 Agent
       Registry (the four verbs), discover by role/capability, and
       every mapped NEXUS module attribute exists for real.
* C — Operations (§15.1): the CodingAgent contract dispatches analyze/
       plan/edit/run/test/debug/review on a real temp project; the test
       op counts passed/failed exactly (either summary order); debug
       names the failing test; edit records the before/after trail.
* D — Coding Loop (§15.6): the eight stages in order, task states
       mapped, events canonical, the debug cycle bounded — the green
       path approves in one cycle, the unfixable path rejects exactly
       at the bound (never an infinite spin).
* E — Session (Cline §15.5, MODE D): the trail records reads, edits
       and tool calls, persists atomically, revives from disk.
* F — Integration + regression: NEXUS_PHASE ≥ 15, nexus-core ≥ 0.15.0,
       the coding core stays stdlib-only, the repository references
       (OpenHands / OpenCode / Cline, MODE B/D) are imported nowhere,
       and the neighbor phase suites (05 · 13 · 14) stay green.

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import importlib
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from coding_project import (  # noqa: E402
    BAD_FIX,
    FAILING_TEST,
    GOOD_FIX,
    MAIN_FIXED,
    make_buggy_project,
)

from nexus import NEXUS_PHASE, __version__  # noqa: E402
from nexus.agents.registry import AgentRegistry  # noqa: E402
from nexus.coding import (  # noqa: E402
    CODING_LOOP_STAGES,
    CODING_OPERATION_KINDS,
    CODING_SPECIALIST_SPECS,
    LOOP_STAGE_ORDER,
    SPECIALIST_ROLES,
    STAGE_TASK_STATES,
    CodingAgent,
    CodingLoop,
    CodingOperationKind,
    CodingSession,
    EditAction,
    OperationRequest,
)

# ================================================================== runner


class Runner:
    """Check counter with the house reporting format."""

    def __init__(self) -> None:
        self.section = ""
        self.passed = 0
        self.failed = 0

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
        print(f"{name} — {self.passed} passed, 0 failed")
        print("=" * 72)
        return 0


# ----------------------------------------------------------------- §15.1/2/6


def section_a(runner: Runner) -> None:
    """Contracts — the verbatim vocabularies and honest validation."""
    runner.section = "A·contracts"
    runner.check(
        "§15.1 the seven operations, verbatim",
        CODING_OPERATION_KINDS
        == ("analyze", "plan", "edit", "run", "test", "debug", "review"),
        detail=f"got {CODING_OPERATION_KINDS}",
    )
    runner.check(
        "§15.2 the ten specialists, verbatim",
        SPECIALIST_ROLES
        == (
            "architect",
            "frontend",
            "backend",
            "database",
            "devops",
            "debugger",
            "tester",
            "security",
            "performance",
            "reviewer",
        ),
        detail=f"got {SPECIALIST_ROLES}",
    )
    runner.check(
        "§15.6 the eight loop stages, verbatim order",
        CODING_LOOP_STAGES
        == (
            "understand",
            "plan",
            "edit",
            "build",
            "test",
            "debug",
            "retest",
            "review",
        ),
        detail=f"got {CODING_LOOP_STAGES}",
    )
    runner.check(
        "§15.6/§2.4 every stage maps to a task state",
        set(STAGE_TASK_STATES) == set(CODING_LOOP_STAGES)
        and all(
            STAGE_TASK_STATES[stage]
            in ("ANALYZING", "PLANNING", "EXECUTING", "VERIFYING", "REPAIRING")
            for stage in CODING_LOOP_STAGES
        ),
    )
    try:
        OperationRequest(kind=cast(CodingOperationKind, "nope"), goal="g")  # refused (the point)
    except Exception:
        runner.check("requests refuse unknown kinds", True)
    else:
        runner.check("requests refuse unknown kinds", False, "no error raised")
    edit = EditAction(path="a.py", old="x", new="y")
    runner.check(
        "EditAction round-trips through dict",
        EditAction.from_dict(edit.to_dict()) == edit,
    )


# ------------------------------------------------------------------- §15.2


def section_b(runner: Runner, tmp: Path) -> None:
    """Specialists — registry integration with real module mappings."""
    runner.section = "B·specialists"
    registry = AgentRegistry(tmp / "agents")
    from nexus.coding.specialists import register_coding_specialists

    agents = register_coding_specialists(registry)
    runner.check("all ten register into the §6.4 registry", len(agents) == 10)
    roles = {a.role for a in registry.discover_agents()}
    runner.check(
        "discoverAgents sees all ten roles",
        roles == set(SPECIALIST_ROLES),
        detail=f"got {sorted(roles)}",
    )
    debugger = registry.discover_agents(role="debugger")
    runner.check(
        "role lookup finds the debugger",
        len(debugger) == 1 and "lesson-recall" in debugger[0].capabilities,
    )
    missing: list[str] = []
    for spec in CODING_SPECIALIST_SPECS:
        for mapping in spec.modules:
            module_name, _, attr = mapping.partition(":")
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                missing.append(mapping)
                continue
            if attr and not hasattr(module, attr):
                missing.append(mapping)
    runner.check(
        "every mapped NEXUS module:attribute exists for real",
        not missing,
        detail=f"missing: {missing}",
    )
    # every specialist serves at least one loop stage
    unattached = [
        spec.role
        for spec in CODING_SPECIALIST_SPECS
        if not any(stage in spec.stages for stage in LOOP_STAGE_ORDER)
    ]
    runner.check("every specialist serves loop stages", not unattached)


# ------------------------------------------------------------------- §15.1


def _request(kind: str, payload: dict | None = None) -> OperationRequest:
    # runtime coerces the string into the enum (the §15.1 contract)
    return OperationRequest(
        kind=cast(CodingOperationKind, kind), goal="gate", payload=payload or {}
    )


def section_c(runner: Runner, project: Path) -> None:
    """Operations — the CodingAgent contract on a real buggy project."""
    runner.section = "C·operations"
    agent = CodingAgent(project)
    analyze = agent.execute(_request("analyze"))
    payload = analyze.payload
    runner.check(
        "analyze answers with files and symbols",
        int(payload.get("files_indexed", 0)) >= 2
        and int(payload.get("symbols", 0)) >= 2,
        detail=f"payload: {payload}",
    )
    test_result = agent.execute(_request("test"))
    tp = test_result.payload
    runner.check(
        "test counts exactly: 1 failed, 1 passed (either summary order)",
        int(tp.get("failed", -1)) == 1 and int(tp.get("passed", -1)) == 1,
        detail=f"failed={tp.get('failed')} passed={tp.get('passed')}",
    )
    runner.check(
        "test names the failing node id",
        FAILING_TEST in (tp.get("failing_tests") or ()),
    )
    debug = agent.execute(_request("debug", {"test_outcome": dict(tp)}))
    findings = debug.payload.get("findings") or ()
    runner.check(
        "debug names the failing test as a finding",
        bool(findings)
        and any(FAILING_TEST in str(f.get("test", "")) for f in findings),
        detail=f"findings: {findings}",
    )
    # arm the trap exactly the way the loop's build stage does: compileall
    # writes the BUGGY bytecode (pytest itself never writes .pyc), and a
    # same-size fix landing in the same mtime second would leave it
    # "valid" — the interpreter would serve old code to the retest.
    import subprocess as _sp  # noqa: PLC0415 — the trap is local to this check

    _sp.run(
        [sys.executable, "-m", "compileall", "-q", str(project)],
        capture_output=True,
        timeout=60,
        check=False,
    )
    edit = agent.execute(
        _request("edit", {"actions": [GOOD_FIX.to_dict()]})
    )
    runner.check(
        "edit applies the fix on disk",
        int(edit.payload.get("applied", 0)) == 1
        and (project / "main.py").read_text(encoding="utf-8") == MAIN_FIXED,
    )
    runner.check(
        "edit purges stale bytecode for the files it writes (the CI's catch)",
        int(edit.payload.get("bytecode_purged", -1)) >= 1
        and not list((project / "__pycache__").glob("main.cpython-*.pyc")),
        detail=f"purged={edit.payload.get('bytecode_purged')}",
    )
    retest = agent.execute(_request("test"))
    runner.check(
        "after the fix the suite is green",
        int(retest.payload.get("failed", 1)) == 0,
    )
    review = agent.execute(
        _request(
            "review",
            {
                "edits_applied": 1,
                "debug_cycles": 1,
                "max_debug_cycles": 3,
            },
        )
    )
    verdict = (review.payload.get("verdict") or {}).get("approved")
    runner.check("review renders the approved verdict", verdict is True)


# ------------------------------------------------------------------- §15.6


def section_d(runner: Runner, tmp: Path) -> None:
    """The loop — stages, states, bounds, verdicts."""
    runner.section = "D·loop"
    project = make_buggy_project(tmp / "loop_workspace")
    agent = CodingAgent(project)
    result = CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    order = tuple(stage.value for stage in LOOP_STAGE_ORDER)
    runner.check(
        "green-after-one-cycle: approved, 8 stages verbatim",
        result.approved
        and result.stage_order == order
        and len(result.stage_traces) == 8,
        detail=f"order={result.stage_order}",
    )
    runner.check(
        "task states follow §2.4 per stage",
        [t.state for t in result.stage_traces]
        == ["ANALYZING", "PLANNING", "EXECUTING", "EXECUTING", "EXECUTING",
            "EXECUTING", "EXECUTING", "VERIFYING"],
    )
    runner.check("one debug cycle used", result.debug_cycles == 1)

    unfix_dir = make_buggy_project(tmp / "unfixable")
    unfix_agent = CodingAgent(unfix_dir)
    unfix = CodingLoop(unfix_agent, unfix_dir, "fix the divide function", 2, fixes=[BAD_FIX]).run()
    runner.check(
        "unfixable: rejected exactly at the bound",
        unfix.approved is False and unfix.debug_cycles == 2,
    )
    runner.check(
        "skeleton stays eight-wide; extra (debug, retest) append",
        unfix.stage_order[:8] == order and unfix.stage_order[8:] == ("debug", "retest"),
        detail=f"order={unfix.stage_order}",
    )
    from nexus.events import CANONICAL_EVENTS

    runner.check(
        "only canonical events emitted",
        set(unfix.events) <= CANONICAL_EVENTS,
        detail=f"non-canonical: {set(unfix.events) - CANONICAL_EVENTS}",
    )


# ------------------------------------------------------------------- §15.5


def section_e(runner: Runner, tmp: Path) -> None:
    """Session — the Cline-inspired trail (MODE D, zero imports)."""
    runner.section = "E·session"
    project = make_buggy_project(tmp / "session_workspace")
    session = CodingSession(goal="gate session", directory=project / "sessions")
    agent = CodingAgent(project, session=session)
    CodingLoop(agent, project, "fix the divide function", 3, fixes=[GOOD_FIX]).run()
    record = session.record
    runner.check(
        "trail records edits and tool calls",
        "main.py" in record.files_edited
        and any(call.name.startswith("coding.") for call in record.tool_calls),
    )
    persisted = session.path
    runner.check("session persisted to disk", persisted is not None and persisted.exists())
    assert persisted is not None  # narrowed for pyright
    revived = CodingSession.load(persisted)
    runner.check(
        "session revives from disk",
        revived.session_id == session.session_id
        and revived.files_edited == record.files_edited,
    )


# ------------------------------------------------- integration + regression


def section_f(runner: Runner, *, regression: bool) -> None:
    """Integration — identity, stdlib-only core, references, regression."""
    runner.section = "F·integration"
    runner.check("NEXUS_PHASE ≥ 15", NEXUS_PHASE >= 15, detail=f"got {NEXUS_PHASE}")
    _v15 = tuple(int(part) for part in "0.15.0".split("."))
    _v_now = tuple(int(part) for part in __version__.split(".")[:3])
    runner.check(
        "nexus-core >= 0.15.0",
        _v_now >= _v15,
        detail=f"got {__version__!r}",
    )
    coding_dir = REPO_ROOT / "nexus" / "coding"
    non_stdlib: list[str] = []
    stdlib_top = set(sys.stdlib_module_names)
    for path in sorted(coding_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level > 0 or not node.module:
                    continue  # relative import within the package
                root = node.module.split(".")[0]
            elif isinstance(node, ast.Import):
                root = node.names[0].name.split(".")[0]
            else:
                continue
            if root not in stdlib_top and root != "nexus":
                non_stdlib.append(f"{path.name}:{root}")
    runner.check(
        "coding core imports stdlib + nexus only",
        not non_stdlib,
        detail=f"non-stdlib: {non_stdlib}",
    )
    banned = ("openhands", "opencode", "cline")
    leak: list[str] = []
    for path in sorted(coding_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8").lower()
        for name in banned:
            if f"import {name}" in source:
                leak.append(f"{path.name}:{name}")
    runner.check("OpenHands/OpenCode/Cline imported nowhere", not leak, detail=str(leak))
    if not regression:
        return
    # the neighbor gates (the house chain: each phase's own harness)
    for phase in ("phase05", "phase13", "phase14"):
        cmd = [sys.executable, f"tests/{phase}/verify_exit_criteria.py"]
        if phase in ("phase13", "phase14"):
            cmd.append("--no-regression")
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )
        runner.check(
            f"regression: {phase} gate green",
            proc.returncode == 0,
            detail=proc.stdout[-300:] if proc.returncode else "",
        )


# ==================================================================== main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-regression",
        action="store_true",
        help="skip the neighbor-suite subprocess regression (CI runs them as steps)",
    )
    args = parser.parse_args()
    print("PHASE 15 — Coding System (New Plan §15) exit criteria")
    runner = Runner()
    with tempfile.TemporaryDirectory(prefix="nexus_p15_") as tmp_name:
        tmp = Path(tmp_name)
        project = make_buggy_project(tmp / "workspace")
        sections = (
            lambda: section_a(runner),
            lambda: section_b(runner, tmp),
            lambda: section_c(runner, project),
            lambda: section_d(runner, tmp),
            lambda: section_e(runner, tmp),
            lambda: section_f(runner, regression=not args.no_regression),
        )
        for section in sections:
            try:
                section()
            except Exception as exc:  # noqa: BLE001 — a section crash is a failure
                print(f"  [FAIL] ({runner.section}) section crashed: {exc}")
                runner.failed += 1
    return runner.summary()


if __name__ == "__main__":
    raise SystemExit(main())
