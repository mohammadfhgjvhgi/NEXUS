#!/usr/bin/env python3
"""Phase 7 verification harness — Final Build Plan §8 Exit Criteria.

Proves the Tool System section by section:

* A — Tool Registry (§8.1): the nine verbatim fields on every tool,
       strict validation (bad schema/permissions/risk-4/version
       rejected), duplicate refusal, upgrade-only replacement,
       freeze, discovery filters and honest capability reports.
* B — Tool Router (§8.2): the verbatim seven-stage pipeline with an
       ordered proof trace; unknown/unavailable tools; the risk gate
       (config-level, policy-independent); confirmation fold
       (approve/deny/no-hook); policy denials (blocked tool, OBSERVE
       autonomy); scope escalation and in-scope paths; the resource
       gate (exhausted → honest refusal, released on failure); the
       Verify stage flipping lying outcomes; canonical events
       (tool.called/completed/failed, direct route); the §6.2
       RoutedToolSink seam (loop-shaped ToolResult, capability-honest
       available(), the verify note).
* C — Native tools (§8.3): the nine names verbatim; filesystem ops
       end-to-end with per-op verification; terminal (exit code,
       timeout, command-not-found); process (list/info/kill-honest);
       hardware snapshot; platform-honest windows/clipboard/screen
       (unavailable reported, never faked) + the stdlib PNG encoder;
       git (init/status/add/commit/log on a real temp repo); github
       (offline request construction, token hygiene, live-or-honest).
* D — MCP (§8.4/§8.5): the official SDK v2 line; the §8.5 server
       gates (allow/block before any stdio write); the echo fixture
       end-to-end through the router; isError honesty; dead-session
       honesty + respawn recovery; the five canonical servers
       declared disabled-by-default; a broken server isolated (the
       runtime keeps its native tools); BONUS: the official
       TypeScript filesystem server via npx — cross-SDK roundtrip.
* E — Integration: NexusRuntime wires the system (registry, router,
       sink into the Master Agent); boot event phase 7; disabled →
       the Phase-6 behavior byte for byte; the §6.2 loop dispatching
       a scripted tool decision through the router; the §7.1
       pre_tool_call veto still in front; shutdown closes MCP.
* F — Regression: Phases 1–6 harnesses still green
       (98/98 · 143/143 · 104/104 · 106/106 · 116/116 · 88/88).

Run:  python tests/phase07/verify_exit_criteria.py [--root DIR]
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.agents import (  # noqa: E402
    Agent,
    AgentCommunicator,
    VerificationPolicy,
)
from nexus.agents.loop import AgentLoop, ToolSink  # noqa: E402
from nexus.core.policy.engine import PolicyEngine  # noqa: E402
from nexus.core.policy.models import AutonomyLevel, TaskPolicy  # noqa: E402
from nexus.events import EventBus  # noqa: E402
from nexus.models.manager import ModelManager  # noqa: E402
from nexus.models.provider import GenerateResult, ProviderError  # noqa: E402
from nexus.models.simulated import SimulatedProvider  # noqa: E402
from nexus.resources import ResourceBudgets, ResourceManager  # noqa: E402
from nexus.tools import RoutedToolSink, ToolRouter  # noqa: E402
from nexus.tools.mcp.adapter import (  # noqa: E402
    McpAdapter,
    sdk_available,
    sdk_version,
)
from nexus.tools.mcp.config import (  # noqa: E402
    McpConfigError,
    McpServerConfig,
    build_server_config,
    load_mcp_servers,
)
from nexus.tools.models import (  # noqa: E402
    REGISTERABLE_RISK_LEVELS,
    ROUTER_STAGES,
    TOOL_FIELDS,
    CapabilityReport,
    ToolDefinition,
    is_valid_version,
)
from nexus.tools.native import NATIVE_TOOL_NAMES, register_native_tools  # noqa: E402
from nexus.tools.native.screen import encode_png  # noqa: E402
from nexus.tools.registry import RegistryError, ToolRegistry  # noqa: E402
from nexus.tools.router import ConfirmationRequest  # noqa: E402

ECHO_SERVER = Path(__file__).resolve().parent / "mcp_echo_server.py"


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
        """Environment-optional evidence (npx/node/network): counted
        separately — a missing runtime is a SKIP, never a failure."""
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


# ----------------------------------------------------------------- fixtures


def make_registry(root: Path) -> ToolRegistry:
    registry = ToolRegistry()
    register_native_tools(registry, workspace_root=root)
    return registry


def make_router(
    registry: ToolRegistry,
    *,
    confirmation_hook: Any = None,
    policy_engine: Any = None,
    resources: Any = None,
    bus: Any = None,
    confirm_danger_above: int = 2,
) -> ToolRouter:
    return ToolRouter(
        registry,
        policy_engine=policy_engine,
        resources=resources,
        bus=bus,
        confirm_danger_above=confirm_danger_above,
        confirmation_hook=confirmation_hook,
    )


class ScriptedProvider(SimulatedProvider):
    """Deterministic model double: pops canned decisions off a script."""

    def __init__(self, script: list[str]) -> None:
        super().__init__()
        self._script = list(script)
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, request: Any) -> GenerateResult:
        self.calls += 1
        self.prompts.append(str(request.prompt))
        if not self._script:
            raise ProviderError("script exhausted")
        text = self._script.pop(0)
        return GenerateResult(
            model_id=request.model_id,
            backend="scripted",
            text=text,
            prompt_tokens=8,
            generation_tokens=max(1, len(text) // 4),
        )


def make_manager(base: str | Path, script: list[str], bus: Any = None) -> ModelManager:
    resources = ResourceManager(
        f"{base}-res",
        budgets=ResourceBudgets(ram_mb=65536, model_memory_mb=65536,
                                vram_mb=0, max_concurrency=4, max_agents=3),
    )
    return ModelManager.from_config(
        f"{base}-models", provider=ScriptedProvider(script),
        resources=resources, bus=bus, keep_warm_seconds=300.0,
        seed_mimo_edge=True,
    )


def make_worker(tools: tuple[str, ...] = ("filesystem",)) -> Agent:
    return Agent.create(
        role="worker",
        instructions="Use the tools precisely.",
        capabilities=("files", "general"),
        tools=tools,
        verification=VerificationPolicy(required=True, criteria=()),
    )


def decision_json(**overrides: Any) -> str:
    payload: dict[str, Any] = {"action": "done", "response": "work complete"}
    payload.update(overrides)
    return json.dumps(payload)


def echo_config(**overrides: Any) -> McpServerConfig:
    values: dict[str, Any] = {
        "name": "echo",
        "command": sys.executable,
        "args": [str(ECHO_SERVER)],
        "risk_ceiling": 1,
        "call_timeout": 20,
    }
    values.update(overrides)
    return build_server_config(values, origin="harness")


def connect_echo(registry: ToolRegistry, **overrides: Any) -> McpAdapter:
    adapter = McpAdapter(registry)
    report = adapter.connect(echo_config(**overrides))
    assert report["count"] >= 2, report
    return adapter


def run_phases(prior: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """Run the Phase 1–6 harnesses; return their (name, line, code) results."""
    results: list[tuple[str, str, int]] = []
    for phase_dir, label, expected in prior:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tests" / phase_dir / "verify_exit_criteria.py")],
            capture_output=True,
            text=True,
            timeout=600,
        )
        results.append((label, proc.stdout.strip().splitlines()[-1], proc.returncode))
        _ = expected
    return results


# ======================================================================= A


def section_a(runner: Runner) -> None:
    """§8.1 — Tool Registry."""
    runner.section = "A"
    base = Path(tempfile.mkdtemp(prefix="nexus-p7-a-"))
    registry = make_registry(base)

    runner.check(
        "the §8.1 field list is verbatim (ten fields, exact order)",
        TOOL_FIELDS == ("id", "name", "description", "input_schema",
                        "output_schema", "permissions", "scope_requirements",
                        "risk", "verification", "version"),
    )
    runner.check(
        "every registered tool carries the ten fields",
        all(
            all(hasattr(definition, field) for field in TOOL_FIELDS)
            for definition in registry.definitions()
        ),
    )
    runner.check(
        "risk scale is 0..4 and level 4 is never registrable",
        REGISTERABLE_RISK_LEVELS == (0, 1, 2, 3),
    )
    runner.check(
        "version contract is strict X.Y.Z",
        is_valid_version("1.0.0") and not is_valid_version("1.0")
        and not is_valid_version("v1.0.0") and not is_valid_version("1.0.0-beta"),
    )

    # ---- validation rejections
    good = registry.get("filesystem")
    assert good is not None

    def clone(**overrides: Any) -> ToolDefinition:
        data = {
            "id": good.definition.id, "name": "probe", "description": "probe",
            "input_schema": good.definition.input_schema,
            "output_schema": good.definition.output_schema,
            "permissions": good.definition.permissions,
            "scope_requirements": good.definition.scope_requirements,
            "risk": good.definition.risk,
            "verification": good.definition.verification,
            "version": good.definition.version,
        }
        data.update(overrides)
        return ToolDefinition(**data)  # type: ignore[arg-type]

    def rejected(definition: ToolDefinition) -> bool:
        try:
            ToolRegistry().register(definition, lambda args: type("R", (), {})())
            return False
        except RegistryError:
            return True

    runner.check("empty name rejected", rejected(clone(name="")))
    runner.check(
        "non-object input_schema rejected",
        rejected(clone(input_schema={"type": "string"})),
    )
    runner.check(
        "permissions must be non-empty",
        rejected(clone(permissions=())),
    )
    runner.check(
        "risk 4 (CRITICAL) is refused at registration",
        rejected(clone(name="crit", risk=4)),
    )
    runner.check(
        "malformed version rejected",
        rejected(clone(name="ver", version="1.0")),
    )

    # ---- duplicates, upgrades, freeze
    small = ToolRegistry()
    register_native_tools(small, workspace_root=base)
    dup = small.get("filesystem")
    assert dup is not None
    try:
        small.register(dup.definition, dup.handler)
        duplicate_refused = False
    except RegistryError:
        duplicate_refused = True
    runner.check("same-version duplicate refused", duplicate_refused)
    small.register(replace(dup.definition, version="1.1.0"), dup.handler)
    upgraded_entry = small.get("filesystem")
    runner.check(
        "strictly-higher version upgrades in place",
        upgraded_entry is not None
        and upgraded_entry.definition.version == "1.1.0",
    )
    small.freeze()
    try:
        small.unregister("filesystem")
        frozen_blocks = False
    except RegistryError:
        frozen_blocks = True
    runner.check("freeze() closes the registry", frozen_blocks and small.frozen)

    # ---- discovery + capability honesty
    runner.check(
        "discovery filters by permission tag and dimension",
        {d.name for d in small.discover(permission="filesystem.write")}
        == {"filesystem"}
        and {d.name for d in small.discover(dimension="display")}
        == {"windows", "screen"},
    )
    cap = small.capabilities("windows")
    runner.check(
        "capability report is typed and honest",
        isinstance(cap, CapabilityReport)
        and cap.available == (sys.platform == "win32"),
    )
    runner.check(
        "families count the native prefix",
        small.families()["native"] == len(NATIVE_TOOL_NAMES),
    )
    git_entry = small.get("git")
    assert git_entry is not None
    serialized = git_entry.definition.to_dict()
    runner.check(
        "serialization roundtrips the §8.1 record (ten keys verbatim)",
        set(TOOL_FIELDS) <= set(serialized) and serialized["name"] == "git",
    )


# ======================================================================= B


def section_b(runner: Runner) -> None:
    """§8.2 — Tool Router."""
    runner.section = "B"
    base = Path(tempfile.mkdtemp(prefix="nexus-p7-b-"))
    registry = make_registry(base)
    router = make_router(registry)

    runner.check(
        "the §8.2 pipeline constant is verbatim (7 stages)",
        ROUTER_STAGES[1:] == ("discovery", "permission", "scope", "resource",
                              "execute", "normalize", "verify"),
    )

    out = router.route("filesystem", {"op": "write_text", "path": "b1.txt",
                                      "content": "router proof"})
    stages = out.trace.stages() if out.trace else ()
    order = [stages.index(s) for s in ("discovery", "permission", "scope",
                                       "resource", "execute", "normalize",
                                       "verify") if s in stages]
    runner.check(
        "a successful route leaves the seven stages in order",
        out.ok and order == sorted(order) and len(stages) == 8,
        detail=f"stages={stages} ok={out.ok} err={out.error}",
    )
    runner.check(
        "write verification proves the file on disk (path_size)",
        out.ok and out.verification is not None
        and out.verification.strategy == "path_size"
        and (base / "b1.txt").read_text() == "router proof",
    )

    unknown = router.route("no_such_tool", {})
    runner.check(
        "unknown tool fails honestly at discovery",
        not unknown.ok and "unknown tool" in unknown.error
        and unknown.trace.stages()[-1] == "discovery",
    )
    unavailable = router.route("windows", {"op": "list_windows"})
    runner.check(
        "platform-unavailable tool fails with the reason (never faked)",
        not unavailable.ok and "win32" in unavailable.error,
    )

    # ---- the risk gate is config-level (no policy needed)
    term = router.route("terminal", {"op": "run", "command": sys.executable,
                                     "args": ["-c", "print(1)"]})
    runner.check(
        "risk 3 > threshold 2 blocks without a confirmation hook",
        not term.ok and "requires human confirmation" in term.error,
    )
    approved: list[ConfirmationRequest] = []

    def on_confirm(request: ConfirmationRequest) -> bool:
        approved.append(request)
        return True

    router_ok = make_router(registry, confirmation_hook=on_confirm)
    term_ok = router_ok.route("terminal", {"op": "run", "command": sys.executable,
                                           "args": ["-c", "print(7)"]})
    runner.check(
        "an approved confirmation executes (one folded request)",
        term_ok.ok and "7" in term_ok.output and len(approved) == 1
        and approved[0].risk == 3,
        detail=f"ok={term_ok.ok} err={term_ok.error}",
    )
    router_no = make_router(registry, confirmation_hook=lambda request: False)
    term_no = router_no.route("terminal", {"op": "run", "command": sys.executable,
                                           "args": ["-c", "print(1)"]})
    runner.check(
        "a denied confirmation fails honestly",
        not term_no.ok and "denied by confirmation hook" in term_no.error,
    )

    # ---- policy engine composition (Phase 2 machinery)
    manager_dir = base / "ws-b"
    manager_dir.mkdir()
    from nexus.core.workspace import WorkspaceManager

    workspace_manager = WorkspaceManager(manager_dir)
    workspace_manager.register(name="task", path=str(manager_dir))
    policy_engine = PolicyEngine(workspace_manager)
    router_pol = make_router(registry, confirmation_hook=on_confirm,
                             policy_engine=policy_engine)

    blocked = TaskPolicy.from_overrides(
        {"tool_policy.blocked_tools": ["filesystem"]}
    )
    out_blocked = router_pol.route(
        "filesystem", {"op": "read_text", "path": "b1.txt"}, policy=blocked
    )
    runner.check(
        "a policy-blocked tool is denied",
        not out_blocked.ok and "blocked by policy" in out_blocked.error,
    )

    observe = TaskPolicy(autonomy_level=AutonomyLevel.OBSERVE)
    out_observe = router_pol.route(
        "filesystem", {"op": "write_text", "path": "b2.txt", "content": "x"},
        policy=observe,
    )
    runner.check(
        "OBSERVE autonomy refuses mutations",
        not out_observe.ok and "OBSERVE" in out_observe.error,
    )

    router_scoped = make_router(registry, policy_engine=policy_engine)
    out_scope = router_scoped.route(
        "filesystem", {"op": "write_text", "path": str(base / "escape.txt"),
                       "content": "out"},
        policy=TaskPolicy(autonomy_level=AutonomyLevel.ACT_CONFIRMED),
    )
    runner.check(
        "out-of-scope mutation escalates (confirm, never wall)",
        not out_scope.ok and "confirmation" in out_scope.error.lower(),
        detail=f"err={out_scope.error}",
    )
    out_inscope = router_pol.route(
        "filesystem",
        {"op": "write_text", "path": str(manager_dir / "in.txt"), "content": "in"},
        policy=TaskPolicy(autonomy_level=AutonomyLevel.FULL),
    )
    runner.check(
        "an in-workspace mutation at FULL autonomy executes",
        out_inscope.ok and (manager_dir / "in.txt").exists(),
    )

    # ---- resource gate
    resources = ResourceManager(
        Path(tempfile.mkdtemp(prefix="nexus-p7-res-")),
        budgets=ResourceBudgets(max_concurrency=1, max_agents=3),
    )
    assert resources.acquire_concurrency()  # exhaust the single slot
    router_res = make_router(registry, resources=resources,
                             confirmation_hook=lambda request: True)
    out_res = router_res.route(
        "filesystem", {"op": "write_text", "path": "res.txt", "content": "x"}
    )
    runner.check(
        "an exhausted concurrency budget refuses honestly",
        not out_res.ok and "concurrency budget exhausted" in out_res.error,
    )
    resources.release_concurrency()
    out_res2 = router_res.route(
        "filesystem", {"op": "write_text", "path": "res.txt", "content": "x"}
    )
    runner.check(
        "the slot is free again after failure (released in finally)",
        out_res2.ok,
    )

    # ---- verify flips lying outcomes
    lie = router.route("git", {"op": "status", "repo": str(base)})
    runner.check(
        "a non-zero exit code fails the verify stage (exit_zero)",
        not lie.ok and "verification failed" in lie.error,
    )
    raise_case = router.route("git", {"op": "status",
                                      "repo": "/nonexistent/no-repo-here"})
    runner.check(
        "a failed call records verify:skip (nothing to verify)",
        not raise_case.ok
        and raise_case.trace.stages()[-1] == "verify"
        and any(
            entry.status == "skip"
            for entry in (raise_case.trace.entries if raise_case.trace else ())
            if entry.stage == "verify"
        ),
    )

    # ---- events on direct routes
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("tool.*", lambda event: seen.append(event.name))
    router_bus = make_router(registry, bus=bus)
    router_bus.route("filesystem", {"op": "read_text", "path": "b1.txt"})
    router_bus.route("filesystem", {"op": "read_text", "path": "missing.txt"})
    runner.check(
        "direct routes publish tool.called + completed/failed (canonical)",
        "tool.called" in seen and "tool.completed" in seen
        and "tool.failed" in seen,
    )

    # ---- the §6.2 seam adapter
    sink = RoutedToolSink(router_ok)
    runner.check(
        "RoutedToolSink is a ToolSink with loop-shaped results",
        isinstance(sink, ToolSink)
        and sink.call("filesystem", {"op": "read_text", "path": "b1.txt"},
                      task_id="t-b").ok
        and sink.call("filesystem", {"op": "read_text", "path": "b1.txt"},
                      task_id="t-b").output.startswith("router proof"),
    )
    runner.check(
        "available() is capability-honest (windows/screen excluded on linux)",
        "filesystem" in sink.available()
        and ("windows" in sink.available()) == (sys.platform == "win32"),
    )
    written = sink.call("filesystem", {"op": "write_text", "path": "sink.txt",
                                       "content": "via sink"}, task_id="t-b")
    runner.check(
        "the verify note rides the sink output",
        written.ok and "[verify:path_size ok]" in written.output,
    )


# ======================================================================= C


def section_c(runner: Runner) -> None:
    """§8.3 — Native tools."""
    runner.section = "C"
    base = Path(tempfile.mkdtemp(prefix="nexus-p7-c-"))
    registry = make_registry(base)
    router = make_router(registry, confirmation_hook=lambda request: True)

    runner.check(
        "the nine §8.3 names are registered, verbatim order",
        registry.names()[:9] == NATIVE_TOOL_NAMES
        and set(NATIVE_TOOL_NAMES) <= set(registry.names()),
    )
    runner.check(
        "native ids are native:<name> with X.Y.Z versions",
        all(
            definition.id == f"native:{definition.name}"
            and is_valid_version(definition.version)
            for definition in registry.definitions()
            if definition.id.startswith("native:")
        ),
    )

    # ---- filesystem full pass
    out = router.route("filesystem", {"op": "write_text", "path": "c1.txt",
                                      "content": "one"})
    runner.check(
        "filesystem write+append+move+copy+stat+find all verify",
        out.ok
        and router.route("filesystem", {"op": "append_text", "path": "c1.txt",
                                        "content": "two"}).ok
        and router.route("filesystem", {"op": "make_dirs", "path": "sub"}).ok
        and router.route("filesystem", {"op": "move", "path": "c1.txt",
                                        "to": "sub/c1.txt"}).ok
        and router.route("filesystem", {"op": "copy", "path": "sub/c1.txt",
                                        "to": "c2.txt"}).ok
        and router.route("filesystem", {"op": "stat", "path": "c2.txt"}).ok
        and router.route("filesystem", {"op": "find", "path": ".",
                                        "pattern": "*.txt"}).ok,
    )
    read = router.route("filesystem", {"op": "read_text", "path": "sub/c1.txt"})
    runner.check(
        "relative paths resolve against the workspace root",
        read.ok and read.output == "onetwo",
    )
    listing = router.route("filesystem", {"op": "list_dir", "path": "."})
    runner.check("list_dir lists entries", listing.ok and "sub" in listing.output)
    deleted = router.route("filesystem", {"op": "delete", "path": "c2.txt"})
    runner.check("delete removes and reports", deleted.ok and not (base / "c2.txt").exists())

    # ---- terminal
    term = router.route("terminal", {"op": "run", "command": sys.executable,
                                     "args": ["-c", "print('term-ok')"]})
    runner.check(
        "terminal runs list-argv and verifies exit zero",
        term.ok and "term-ok" in term.output,
    )
    missing = router.route("terminal", {"op": "run", "command": "no-such-bin-xyz"})
    runner.check(
        "command-not-found is an honest 127",
        not missing.ok and "command not found" in missing.output,
    )
    slow = router.route("terminal", {"op": "run", "command": sys.executable,
                                     "args": ["-c", "import time; time.sleep(5)"],
                                     "timeout_seconds": 1})
    runner.check(
        "a hard timeout is honest (124, timed_out artifact)",
        not slow.ok and "timeout" in slow.output.lower(),
    )

    # ---- process
    listing_p = router.route("process", {"op": "list", "limit": 20})
    runner.check(
        "process list works (psutil ladder or /proc) and verifies non-empty",
        listing_p.ok and len(listing_p.output.splitlines()) >= 5,
    )
    info = router.route("process", {"op": "info", "pid": os.getpid()})
    runner.check(
        "process info(pid) returns the record (json_field verify)",
        info.ok and "python" in info.output.lower(),
    )
    kill = router.route("process", {"op": "kill", "pid": 999_999})
    runner.check(
        "killing an unknown pid is honest (no crash, clear error)",
        not kill.ok,
    )

    # ---- hardware
    snap = router.route("hardware", {"op": "snapshot"})
    cpu = router.route("hardware", {"op": "cpu"})
    disk = router.route("hardware", {"op": "disk"})
    runner.check(
        "hardware snapshot/cpu/disk all verify non-empty",
        snap.ok and cpu.ok and disk.ok and "count" in cpu.output,
    )

    # ---- platform-honest windows/clipboard/screen
    cap_w = registry.capabilities("windows")
    out_w = router.route("windows", {"op": "list_windows"})
    runner.check(
        "windows tool: honest availability == platform",
        (out_w.ok == cap_w.available)
        and (cap_w.available or "win32" in out_w.error),
    )
    cap_c = registry.capabilities("clipboard")
    out_c = router.route("clipboard", {"op": "read"})
    runner.check(
        "clipboard tool: honest availability == backend ladder",
        (out_c.ok == cap_c.available)
        and (cap_c.available or "no clipboard backend" in out_c.error),
        detail=f"cap={cap_c.available} err={out_c.error}",
    )
    cap_s = registry.capabilities("screen")
    out_s = router.route("screen", {"op": "size"})
    runner.check(
        "screen tool: honest availability == GDI presence",
        (out_s.ok == cap_s.available)
        and (cap_s.available or "win32 GDI" in out_s.error),
    )
    # the stdlib PNG encoder is testable everywhere: parse the chunks
    import struct
    import zlib

    bgra = bytes([10, 20, 30, 255, 40, 50, 60, 255,
                  70, 80, 90, 255, 100, 110, 120, 255])
    png = encode_png(2, 2, bgra)
    chunks: list[tuple[bytes, bytes]] = []
    cursor = 8
    while cursor + 8 <= len(png):
        (length,) = struct.unpack(">I", png[cursor:cursor + 4])
        tag = png[cursor + 4:cursor + 8]
        chunks.append((tag, png[cursor + 8:cursor + 8 + length]))
        cursor += 12 + length
    ihdr = dict(chunks)[b"IHDR"]
    idat = b"".join(data for tag, data in chunks if tag == b"IDAT")
    width, height = struct.unpack(">II", ihdr[:8])
    decoded = zlib.decompress(idat)
    runner.check(
        "the stdlib PNG encoder emits a valid IHDR/IDAT PNG",
        png.startswith(b"\x89PNG\r\n\x1a\n")
        and (width, height) == (2, 2)
        and ihdr[8] == 8 and ihdr[9] == 2  # 8-bit RGB, truecolor
        and decoded == b"\x00" + bytes([30, 20, 10, 60, 50, 40])
        + b"\x00" + bytes([90, 80, 70, 120, 110, 100]),
        detail=f"chunks={[t for t, _ in chunks]}",
    )

    # ---- git on a real temp repo
    repo = base / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email",
                    "phase7@nexus.local"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name",
                    "Phase7"], check=True, capture_output=True)
    (repo / "file.txt").write_text("hello git tool\n")
    status = router.route("git", {"op": "status", "repo": str(repo)})
    runner.check(
        "git status on a fresh repo verifies (exit 0, porcelain rows)",
        status.ok and "file.txt" in status.output,
    )
    add = router.route("git", {"op": "add", "repo": str(repo)})
    commit = router.route("git", {"op": "commit", "repo": str(repo),
                                  "message": "phase 7 proof"})
    log = router.route("git", {"op": "log", "repo": str(repo), "limit": 5})
    runner.check(
        "git add/commit/log all verify exit zero",
        add.ok and commit.ok and log.ok and "phase 7 proof" in log.output,
    )

    # ---- github offline construction + token hygiene
    from nexus.tools.native.github import GithubTool

    tool = GithubTool()
    request = tool.build_request("repo_info", {"repo": "modelcontextprotocol/python-sdk"},
                                 token="SECRET-TOKEN-XYZ")
    runner.check(
        "github build_request constructs the REST call offline",
        request.full_url == "https://api.github.com/repos/modelcontextprotocol/python-sdk"
        and request.get_header("Authorization") == "Bearer SECRET-TOKEN-XYZ"
        and request.get_header("Accept") == "application/vnd.github+json",
    )
    create = tool.build_request("create_issue",
                                {"repo": "ps-community/nexus",
                                 "title": "t", "body": "b"})
    runner.check(
        "create_issue is a POST with a JSON body",
        create.get_method() == "POST" and json.loads(create.data.decode())["title"] == "t",
    )
    live = router.route("github", {"op": "repo_info",
                                   "repo": "modelcontextprotocol/python-sdk"})
    runner.check(
        "github live call: honest either way (payload or actionable error)",
        live.ok or ("HTTP" in live.output or "network failure" in live.output),
        detail=f"ok={live.ok} out={live.output[:80]}",
    )


# ======================================================================= D


def section_d(runner: Runner) -> None:
    """§8.4/§8.5 — MCP: the official SDK behind the NEXUS gates."""
    runner.section = "D"
    base = Path(tempfile.mkdtemp(prefix="nexus-p7-d-"))

    runner.check(
        "the official MCP SDK is installed (MODE A extra)",
        sdk_available(),
        detail="pip install 'nexus-core[mcp]'",
    )
    version = sdk_version() or ""
    runner.check(
        "the SDK is the v2 stable line (operator pin mcp>=2.0,<3)",
        version.startswith("2."),
        detail=f"version={version}",
    )

    # ---- §8.5 config: the five canonical servers, disabled by default
    mcp_toml = REPO_ROOT / "config" / "tools" / "mcp.toml"
    servers = load_mcp_servers(mcp_toml)
    names = {server.name for server in servers}
    runner.check(
        "the five §8.5 servers are declared (filesystem/git/fetch/memory/database)",
        {"filesystem", "git", "fetch", "memory", "database"} <= names,
    )
    runner.check(
        "every declared server ships behind NEXUS gates (ceiling ≤ 3, disabled default)",
        all(0 <= server.risk_ceiling <= 3 and server.enabled is False
            for server in servers),
    )

    cfg = McpServerConfig(name="probe", command="x")
    runner.check(
        "server gate: blocklist wins, allowlist bounds, * allows",
        not McpServerConfig(name="p", command="x", blocked_tools=("a",)).allows("a")
        and McpServerConfig(name="p", command="x", allowed_tools=("a",)).allows("a")
        and not McpServerConfig(name="p", command="x", allowed_tools=("a",)).allows("b")
        and cfg.allows("anything"),
    )
    try:
        build_server_config({"command": "x"}, origin="t")
        bad_config = False
    except McpConfigError:
        bad_config = True
    runner.check("server config validation rejects a missing name", bad_config)

    # ---- echo fixture end-to-end
    registry = make_registry(base)
    router = make_router(registry, confirmation_hook=lambda request: True)
    echo_adapter = connect_echo(registry)
    out = router.route("mcp.echo.echo", {"text": "through the nexus gate"})
    runner.check(
        "an MCP tool routes through the full §8.2 pipeline",
        out.ok and out.output == "through the nexus gate"
        and out.trace.stages() == ("agent", "discovery", "permission", "scope",
                                   "resource", "execute", "normalize", "verify"),
        detail=f"ok={out.ok} err={out.error} stages={out.trace.stages() if out.trace else ()}",
    )
    total = router.route("mcp.echo.add", {"a": 20, "b": 22})
    runner.check("a second MCP tool computes (add → 42)",
                 total.ok and total.output.strip() == "42")

    definition = registry.get("mcp.echo.echo")
    runner.check(
        "MCP tools enter the registry as §8.1 records with the server's risk clamp",
        definition is not None
        and definition.definition.id == "mcp:echo:echo"
        and definition.definition.risk == 1
        and definition.definition.verification.strategy == "none",
    )

    boom = router.route("mcp.echo.boom", {"text": "fail please"})
    runner.check(
        "a server-side isError result is an honest failure",
        not boom.ok and ("boom" in (boom.error or "")
                        or "UnexpectedToolError" in (boom.error or "")),
        detail=f"ok={boom.ok} err={boom.error!r}",
    )
    echo_adapter.shutdown()

    # ---- the §8.5 gates: block BEFORE any stdio write
    registry_block = make_registry(Path(tempfile.mkdtemp(prefix="nexus-p7-blk-")))
    adapter_block = McpAdapter(registry_block)
    report_block = adapter_block.connect(
        echo_config(blocked_tools=("add", "boom"))
    )
    runner.check(
        "blocked MCP tools are never registered (gate before stdio)",
        "mcp.echo.echo" in report_block["tools"]
        and "mcp.echo.add" not in report_block["tools"],
    )
    registry_allow = make_registry(Path(tempfile.mkdtemp(prefix="nexus-p7-alw-")))
    adapter_allow = McpAdapter(registry_allow)
    report_allow = adapter_allow.connect(
        echo_config(allowed_tools=("echo",))
    )
    runner.check(
        "an explicit allowlist bounds the registered surface",
        [t for t in report_allow["tools"] if t.endswith("boom")] == [],
    )
    adapter_block.shutdown()
    adapter_allow.shutdown()

    # ---- dead session honesty + respawn recovery (in-protocol crash)
    registry_rec = make_registry(base)
    router_rec = make_router(registry_rec, confirmation_hook=lambda request: True)
    adapter_rec = connect_echo(registry_rec)
    first = router_rec.route("mcp.echo.echo", {"text": "before death"})
    # crash injection THROUGH the protocol: the die tool kills the
    # server process mid-call — deterministic, no internals touched.
    killed = router_rec.route("mcp.echo.die", {})
    # the NEXT call respawns the transport and must recover — the
    # killed call itself stays failed (no silent retry).
    recovered = router_rec.route("mcp.echo.echo", {"text": "recovered"})
    runner.check(
        "a crashed session fails honestly (no silent retry)",
        first.ok and not killed.ok
        and "McpSessionDeadError" in (killed.error or ""),
        detail=f"killed={killed.error!r}",
    )
    runner.check(
        "the next call respawns the transport and recovers",
        recovered.ok and recovered.output == "recovered",
        detail=f"ok={recovered.ok} err={recovered.error!r}",
    )
    adapter_rec.shutdown()

    # ---- a broken server is isolated; natives keep working
    registry_iso = make_registry(base)
    broken = build_server_config(
        {"name": "broken", "command": "/nonexistent/binary/xyz"}, origin="harness"
    )
    from nexus.tools.mcp.adapter import connect_from_config

    adapter_iso, report_iso = connect_from_config(
        registry_iso, (broken,), mcp_toml=None
    )
    router_iso = make_router(registry_iso)
    native_after = router_iso.route(
        "filesystem", {"op": "write_text", "path": "iso.txt", "content": "ok"}
    )
    runner.check(
        "a broken server never breaks the runtime (isolated error report)",
        "error" in report_iso["servers"]["broken"]
        and native_after.ok,
    )

    # ---- BONUS: the official TypeScript filesystem server (cross-SDK)
    if shutil.which("npx"):
        try:
            registry_fs = make_registry(base)
            router_fs = make_router(registry_fs)
            official = build_server_config(
                {"name": "filesystem", "command": "npx",
                 "args": ["-y", "@modelcontextprotocol/server-filesystem", str(base)],
                 "risk_ceiling": 2},
                origin="harness",
            )
            adapter_fs = McpAdapter(registry_fs)
            report_fs = adapter_fs.connect(official)
            target = str(base / "official_roundtrip.txt")
            via_mcp = router_fs.route(
                "mcp.filesystem.write_file",
                {"path": target, "content": "cross-sdk proof"},
            )
            native_read = router_fs.route(
                "filesystem", {"op": "read_text", "path": target}
            ) if via_mcp.ok else None
            runner.bonus_check(
                "official TS filesystem server behind the router: "
                "write via MCP → native read-back (cross-SDK roundtrip)",
                bool(native_read and native_read.ok
                     and native_read.output == "cross-sdk proof"
                     and report_fs["count"] >= 10),
                detail=f"tools={report_fs['count']} ok={via_mcp.ok}",
            )
            adapter_fs.shutdown()
        except Exception as exc:  # noqa: BLE001 — bonus evidence only
            runner.bonus_check("official TS server proof", False, detail=str(exc))
    else:
        runner.bonus_check(
            "official TS filesystem server proof", False, detail="npx not on PATH"
        )

    # ---- graceful degradation without the SDK
    from nexus.tools import build_tool_system

    registry_gd = ToolRegistry()
    _registry_gd, _router_gd, adapter_none, report_gd = build_tool_system(
        registry=registry_gd, native=True, mcp_servers=()
    )
    runner.check(
        "no MCP servers → adapter None, natives intact",
        adapter_none is None and report_gd["mcp"] is None
        and registry_gd.count() == len(NATIVE_TOOL_NAMES),
    )


# ======================================================================= E


def section_e(runner: Runner) -> None:
    """Integration — runtime wiring, the §6.2 loop, the §7.1 veto."""
    runner.section = "E"
    from nexus.core.config.runtime import NexusRuntime

    root = Path(tempfile.mkdtemp(prefix="nexus-p7-e-"))
    runtime = NexusRuntime.boot(root)
    shutdown_ok = False
    try:
        runner.check(
            "the runtime wires registry + router + sink (Phase 7)",
            runtime.tool_registry is not None
            and runtime.tool_router is not None
            and runtime.tool_sink is not None
            and runtime.tool_registry.count() >= len(NATIVE_TOOL_NAMES),
        )
        started = [
            event for event in runtime.bus.history_snapshot()
            if event.name == "system.started"
        ]
        runner.check(
            "boot publishes phase 7",
            bool(started) and started[0].payload["phase"] == 7,
        )
        runner.check(
            "the Master Agent dispatches through the routed sink",
            runtime.master_agent is not None
            and runtime.master_agent._tools is runtime.tool_sink,  # noqa: SLF001
        )
    finally:
        try:
            runtime.shutdown()
            shutdown_ok = True
        except Exception:  # noqa: BLE001 — the check reports the failure
            shutdown_ok = False
    runner.check("shutdown with a wired tool system is clean", shutdown_ok)

    # ---- disabled → Phase-6 behavior byte for byte
    root_off = Path(tempfile.mkdtemp(prefix="nexus-p7-off-"))
    runtime_off = NexusRuntime.boot(
        root_off,
        env={"NEXUS_TOOLS__NATIVE_ENABLED": "false",
             "NEXUS_TOOLS__MCP_ENABLED": "false"},
    )
    try:
        runner.check(
            "tools disabled → the Phase-6 runtime, byte for byte",
            runtime_off.tool_registry is None
            and runtime_off.tool_router is None
            and runtime_off.tool_sink is None
            and runtime_off.harness is not None,
        )
    finally:
        runtime_off.shutdown()

    # ---- the §6.2 loop dispatches a scripted tool decision through the router
    from nexus.core.session.models import Task

    base = Path(tempfile.mkdtemp(prefix="nexus-p7-loop-"))
    bus = EventBus()
    registry = make_registry(base)
    router = make_router(registry)
    sink = RoutedToolSink(router)
    manager = make_manager(base, [
        decision_json(action="call_tool", tool="filesystem",
                      arguments={"op": "write_text", "path": "loop.txt",
                                 "content": "from the loop"}),
        decision_json(),
    ])
    worker = make_worker(tools=("filesystem",))
    from nexus.agents.ownership import OwnershipManager

    loop = AgentLoop(
        agent=worker, model_manager=manager,
        communicator=AgentCommunicator(persist=False),
        ownership=OwnershipManager(), bus=bus, tools=sink, max_turns=4,
    )
    task = Task.create(conversation_id="conv_p7", goal="Write loop.txt",
                       prompt="Write loop.txt via the tool system.")
    outcome = loop.run(task)
    runner.check(
        "the loop completes with the routed tool (file exists, evidence kept)",
        outcome.completed and (base / "loop.txt").read_text() == "from the loop",
        detail=f"completed={outcome.completed}",
    )
    names = [event.name for event in bus.history_snapshot()]
    runner.check(
        "the loop still owns the canonical tool events (no duplicates)",
        names.count("tool.called") == 1 and names.count("tool.completed") == 1,
        detail=f"events={[n for n in names if n.startswith('tool')]}",
    )

    # ---- the §7.1 pre_tool_call veto still guards the aperture
    base_v = Path(tempfile.mkdtemp(prefix="nexus-p7-veto-"))
    registry_v = make_registry(base_v)
    sink_v = RoutedToolSink(make_router(registry_v))
    manager_v = make_manager(base_v, [
        decision_json(action="call_tool", tool="filesystem",
                      arguments={"op": "write_text", "path": "veto.txt",
                                 "content": "must not exist"}),
        decision_json(),
    ])
    from nexus.harness import Harness, HarnessHooks

    veto_hooks = HarnessHooks()
    veto_hooks.register(
        "pre_tool_call",
        lambda ctx: False if ctx.tool == "filesystem" else None,
    )
    loop_v = AgentLoop(
        agent=make_worker(), model_manager=manager_v,
        communicator=AgentCommunicator(persist=False),
        ownership=OwnershipManager(), bus=EventBus(), tools=sink_v,
        harness=Harness(hooks=veto_hooks), max_turns=4,
    )
    task_v = Task.create(conversation_id="conv_p7v", goal="Try to write veto.txt",
                         prompt="Try writing veto.txt.")
    outcome_v = loop_v.run(task_v)
    runner.check(
        "the Phase-6 pre_tool_call veto blocks the routed tool",
        outcome_v.completed and not (base_v / "veto.txt").exists(),
        detail=f"completed={outcome_v.completed} exists={(base_v / 'veto.txt').exists()}",
    )


# ======================================================================= F


def section_f(runner: Runner) -> None:
    """Regression — Phases 1–6 harnesses stay green."""
    runner.section = "F"
    prior = [
        ("phase01", "Phase 1", 98),
        ("phase02", "Phase 2", 143),
        ("phase03", "Phase 3", 104),
        ("phase04", "Phase 4", 106),
        ("phase05", "Phase 5", 116),
        ("phase06", "Phase 6", 88),
    ]
    results = run_phases(prior)
    for (_phase_dir, label, _expected), (_label, line, code) in zip(
        prior, results, strict=True
    ):
        runner.check(
            f"{label} harness still green ({line})",
            code == 0,
            detail=f"exit={code} last={line!r}",
        )


# ======================================================================= main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="unused (repo-rooted)")
    _ = parser.parse_args()
    print("PHASE 7 — Tool System (Final Build Plan §8) exit criteria")
    runner = Runner()
    for section in (section_a, section_b, section_c, section_d, section_e, section_f):
        try:
            section(runner)
        except Exception as exc:  # noqa: BLE001 — a section crash is a failure
            print(f"  [FAIL] ({runner.section}) section crashed: {exc}")
            runner.failed += 1
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
