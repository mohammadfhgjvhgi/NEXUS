#!/usr/bin/env python3
"""Phase 2 verification harness — Final Build Plan §3 Exit Criteria.

Proves Workspace + Scope + Policy section by section:

* A — Workspace Manager (§3.1): the seven fields, unique names,
       atomic registry persistence, path resolution.
* B — Scope Model (§3.2): the six dimensions, coverage checks,
       merge, the ``Task.scope`` mapping bridge.
* C — Scope Resolution (§3.3): "اشتغل على M:\\Client" → workspace
       Client, filesystem scope M:\\Client (verbatim plan example).
* D — Cross-workspace Access (§3.4): never an absolute block —
       scoped, audited access to the requested part only.
* E — Task Policy (§3.5): the nine components, defaults, overrides,
       serialization round-trip.
* F — Policy Engine + Integration: allow/confirm/deny matrix,
       runtime wiring, workspace persistence across restarts, and
       the Phase 1 harness still green (98/98).

Run:  python tests/phase02/verify_exit_criteria.py [--root DIR]
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.core.config import NexusRuntime  # noqa: E402
from nexus.core.policy import (  # noqa: E402
    POLICY_COMPONENTS,
    ActionType,
    AutonomyLevel,
    PolicyAction,
    PolicyEngine,
    TaskPolicy,
)
from nexus.core.scope import (  # noqa: E402
    SCOPE_DIMENSIONS,
    Scope,
    ScopeEngine,
    keywords_for,
    path_tokens,
)
from nexus.core.workspace import (  # noqa: E402
    DEFAULT_WORKSPACE_ID,
    REGISTRY_SCHEMA,
    REGISTRY_VERSION,
    Workspace,
    WorkspaceError,
    WorkspaceManager,
)
from nexus.events import EventBus  # noqa: E402

# --- verbatim expectations from the Final Build Plan -----------------------

PLAN_WORKSPACE_FIELDS = [
    "id", "name", "path", "project",
    "memory_namespace", "git_repository", "settings",
]

PLAN_SCOPE_DIMENSIONS = [
    "filesystem_paths",
    "applications",
    "browser_sessions",
    "network_permissions",
    "tools",
    "repositories",
]

PLAN_POLICY_COMPONENTS = [
    "autonomy_level",
    "time_policy",
    "network_policy",
    "tool_policy",
    "workspace_scope",
    "app_scope",
    "git_policy",
    "external_ai_policy",
    "resource_policy",
]

# The §3.3 verbatim resolution example.
PLAN_RESOLVE_REQUEST = "اشتغل على M:\\Client"


class Runner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.section = "?"

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        status = "PASS" if condition else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{status}] ({self.section}) {label}{suffix}")
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def summary(self) -> int:
        total = self.passed + self.failed
        print()
        print("=" * 72)
        print(f"PHASE 2 EXIT CRITERIA — {self.passed}/{total} checks passed"
              f" ({self.failed} failed)")
        print("=" * 72)
        return 0 if self.failed == 0 else 1


class Recorder:
    """Subscribes to '*' and records event names."""

    def __init__(self, bus: EventBus) -> None:
        self.names: list[str] = []
        bus.subscribe("*", lambda event: self.names.append(event.name))


def make_registry(base: Path) -> WorkspaceManager:
    """The standard four-workspace registry used by sections A–D."""
    manager = WorkspaceManager(base / "workspaces")
    manager.register(
        name="Client",
        path="M:\\Client",
        project="ClientWebsite",
        git_repository="https://github.com/acme/client.git",
        settings={
            "applications": ["VS Code", "Chrome"],
            "tools": ["terminal", "git", "github"],
            "browser_sessions": ["browse-1"],
            "network_permissions": ["api.github.com"],
        },
    )
    manager.register(name="Android", path="/home/user/AndroidProject")
    manager.register(name="Site", path="M:\\Client\\site")
    manager.register(
        name="NEXUS",
        path="M:\\NEXUS",
        git_repository="https://github.com/PS-COMMUNITY/nexus.git",
        settings={
            "applications": ["VS Code"],
            "tools": ["git", "github"],
            "browser_sessions": ["browse-9"],
        },
    )
    return manager


def section_a(runner: Runner, base: Path) -> WorkspaceManager:
    """A — Workspace Manager (§3.1)."""
    runner.section = "A/§3.1"

    # object shape — the seven verbatim fields
    runner.check("seven §3.1 fields, verbatim order",
                 [f.name for f in Workspace.__dataclass_fields__.values()
                  if f.name in PLAN_WORKSPACE_FIELDS] == PLAN_WORKSPACE_FIELDS)
    ws = Workspace.create(name="Client", path="M:\\Client")
    runner.check("id prefix wsp_ + 12 hex",
                 ws.id.startswith("wsp_") and len(ws.id) == 16
                 and all(c in "0123456789abcdef" for c in ws.id[4:]))
    runner.check("project defaults to name", ws.project == "Client")
    runner.check("memory_namespace defaults to nexus.memory.<name>",
                 ws.memory_namespace == "nexus.memory.client")
    runner.check("git_repository defaults to None", ws.git_repository is None)
    runner.check("settings defaults to empty dict", ws.settings == {})
    ws2 = Workspace.create(name="X", path="M:\\X", project="ProjectX",
                           memory_namespace="custom.ns",
                           git_repository="https://example.com/x.git",
                           settings={"k": 1})
    runner.check("explicit fields preserved",
                 ws2.project == "ProjectX" and ws2.memory_namespace == "custom.ns"
                 and ws2.git_repository == "https://example.com/x.git"
                 and ws2.settings == {"k": 1})

    # validation
    try:
        Workspace.create(name="", path="M:\\A")
        runner.check("empty name rejected", False)
    except WorkspaceError:
        runner.check("empty name rejected", True)
    try:
        Workspace.create(name="A", path="   ")
        runner.check("empty path rejected", False)
    except WorkspaceError:
        runner.check("empty path rejected", True)
    try:
        Workspace.create(name="A", path="M:\\A", workspace_id="wsp_nothex00")
        runner.check("invalid id rejected (reserved default id protected)",
                     False)
    except WorkspaceError:
        runner.check("invalid id rejected (reserved default id protected)",
                     True)

    # registry: registration, uniqueness, persistence
    manager = WorkspaceManager(base / "reg-a")
    manager.register(name="Alpha", path="M:\\Alpha")
    try:
        manager.register(name="alpha", path="M:\\Other")
        runner.check("duplicate name rejected (case-insensitive)", False)
    except WorkspaceError:
        runner.check("duplicate name rejected (case-insensitive)", True)

    reloaded = WorkspaceManager(base / "reg-a")
    runner.check("registry persists and reloads", reloaded.count() == 1)
    alpha = reloaded.get_by_name("Alpha")
    runner.check("round-trip keeps all seven fields",
                 alpha is not None and alpha.path == "M:\\Alpha"
                 and alpha.project == "Alpha"
                 and alpha.memory_namespace == "nexus.memory.alpha")
    runner.check("registry file schema/version",
                 reloaded.registry_path.is_file()
                 and REGISTRY_SCHEMA == "nexus.workspaces.registry"
                 and REGISTRY_VERSION == 1)

    # lookups
    runner.check("get by id", reloaded.get(alpha.id).name == "Alpha")
    try:
        reloaded.get("wsp_000000000000")
        runner.check("unknown id raises WorkspaceError", False)
    except WorkspaceError:
        runner.check("unknown id raises WorkspaceError", True)
    runner.check("find by name and by id",
                 reloaded.find("alpha") is not None
                 and reloaded.find(alpha.id) is not None
                 and reloaded.find("ghost") is None)
    runner.check("list sorted by name",
                 [w.name for w in make_registry(base / "reg-sort").list_workspaces()]
                 == ["Android", "Client", "NEXUS", "Site"])

    # path resolution — the §3.3 primitive
    full = make_registry(base / "reg-p")
    runner.check("resolve_path root exact",
                 full.resolve_path("M:\\Client").name == "Client")
    runner.check("resolve_path deep child",
                 full.resolve_path("M:\\Client\\src\\app.py").name == "Client")
    runner.check("resolve_path longest root wins",
                 full.resolve_path("M:\\Client\\site\\index.html").name == "Site")
    runner.check("resolve_path POSIX root",
                 full.resolve_path("/home/user/AndroidProject/app").name
                 == "Android")
    runner.check("resolve_path case/slash tolerant",
                 full.resolve_path("m:/client").name == "Client")
    runner.check("resolve_path unknown → None",
                 full.resolve_path("C:\\Windows") is None)

    # update / remove (on the registry that owns Alpha)
    owner = WorkspaceManager(base / "reg-a")
    owner.register(name="Beta", path="M:\\Beta")
    updated = owner.update(
        alpha.id,
        name="AlphaPrime",
        git_repository="https://g.co/a.git",
        settings={"level": 2},
    )
    runner.check("update renames + sets git + merges settings",
                 updated.name == "AlphaPrime"
                 and updated.git_repository == "https://g.co/a.git"
                 and updated.settings == {"level": 2})
    runner.check("update persists",
                 WorkspaceManager(base / "reg-a").get_by_name("AlphaPrime")
                 is not None)
    try:
        owner.update(alpha.id, name="Beta")
        runner.check("rename to duplicate rejected", False)
    except WorkspaceError:
        runner.check("rename to duplicate rejected", True)
    removed = owner.remove(alpha.id)
    runner.check("remove returns the workspace", removed.id == alpha.id)
    runner.check("removed workspace is gone", owner.find(alpha.id) is None)

    # default workspace
    empty = WorkspaceManager(base / "reg-empty")
    synthetic = empty.default()
    runner.check("default is synthetic when unregistered",
                 synthetic.id == DEFAULT_WORKSPACE_ID and synthetic.name == "main")
    with_main = WorkspaceManager(base / "reg-main")
    with_main.register(name="main", path="M:\\Main")
    runner.check("default returns the registered one",
                 with_main.default().path == "M:\\Main")

    # serialization round-trip
    record = ws2.to_dict()
    rebuilt = Workspace.from_dict(record)
    runner.check("to_dict/from_dict round-trip",
                 rebuilt.project == ws2.project
                 and rebuilt.memory_namespace == ws2.memory_namespace
                 and rebuilt.git_repository == ws2.git_repository
                 and rebuilt.settings == ws2.settings)
    return full


def section_b(runner: Runner, manager: WorkspaceManager) -> Scope:
    """B — Scope Model (§3.2)."""
    runner.section = "B/§3.2"

    runner.check("six dimensions, verbatim order",
                 list(SCOPE_DIMENSIONS) == PLAN_SCOPE_DIMENSIONS)
    scope = Scope.create(
        filesystem_paths=["M:\\A", "M:\\A", " "],
        tools=["git", "Git", "terminal"],
        repositories=["https://example.com/r.git"],
    )
    runner.check("create cleans, dedupes, drops empties",
                 scope.filesystem_paths == ["M:\\A"]
                 and scope.tools == ["git", "terminal"]
                 and scope.repositories == ["https://example.com/r.git"])
    runner.check("unknown dimension keys ignored",
                 Scope.create(nonsense=["x"]) is not None)

    client = manager.get_by_name("Client")
    derived = Scope.from_workspace(client)
    runner.check("from_workspace: fs scope = the workspace root",
                 derived.filesystem_paths == ["M:\\Client"])
    runner.check("from_workspace: repositories from git_repository",
                 derived.repositories == ["https://github.com/acme/client.git"])
    runner.check("from_workspace: operational dimensions from settings",
                 derived.applications == ["VS Code", "Chrome"]
                 and derived.tools == ["terminal", "git", "github"]
                 and derived.browser_sessions == ["browse-1"]
                 and derived.network_permissions == ["api.github.com"])
    android = manager.get_by_name("Android")
    bare = Scope.from_workspace(android)
    runner.check("workspace without git/settings → empty non-fs dimensions",
                 bare.repositories == [] and bare.applications == []
                 and bare.tools == [] and bare.network_permissions == [])

    # coverage
    runner.check("covers_path child + root, case/slash tolerant",
                 derived.covers_path("M:\\Client\\src\\app.py")
                 and derived.covers_path("m:/client")
                 and not derived.covers_path("M:\\ClientOther\\x"))
    runner.check("covers_host wildcard",
                 Scope(network_permissions=["*"]).covers_host("anything.io"))
    runner.check("covers_host suffix rule",
                 Scope(network_permissions=["github.com"]).covers_host(
                     "api.github.com")
                 and not Scope(network_permissions=["github.com"]).covers_host(
                     "raw.githubusercontent.com"))
    runner.check("covers_host *.domain rule",
                 Scope(network_permissions=["*.internal.local"]).covers_host(
                     "db.internal.local")
                 and not Scope(network_permissions=["*.internal.local"]).covers_host(
                     "internal.local.evil.com"))
    runner.check("covers_tool exact + case-insensitive + wildcard",
                 derived.covers_tool("git") and derived.covers_tool("GitHub")
                 and Scope(tools=["*"]).covers_tool("blender"))
    runner.check("covers_application",
                 derived.covers_application("chrome")
                 and not derived.covers_application("word"))
    runner.check("covers_browser_session",
                 derived.covers_browser_session("browse-1")
                 and not derived.covers_browser_session("browse-2"))
    runner.check("covers_repository",
                 derived.covers_repository("https://github.com/acme/client.git")
                 and Scope(repositories=["*"]).covers_repository("any"))

    # algebra + bridge
    merged = derived.merge(Scope(tools=["blender"], applications=["Word"]))
    runner.check("merge unions per dimension",
                 "blender" in merged.tools and "git" in merged.tools
                 and "Word" in merged.applications and "VS Code" in merged.applications)
    scope_map = derived.to_scope_map()
    runner.check("to_scope_map: the six §3.2 keys",
                 list(scope_map) == PLAN_SCOPE_DIMENSIONS)
    rebuilt = Scope.from_scope_map(scope_map)
    runner.check("from_scope_map round-trip",
                 rebuilt.to_scope_map() == scope_map)
    runner.check("is_empty",
                 Scope.empty().is_empty() and not derived.is_empty())
    return derived


def section_c(runner: Runner, manager: WorkspaceManager, engine: ScopeEngine) -> None:
    """C — Scope Resolution (§3.3)."""
    runner.section = "C/§3.3"

    resolution = engine.resolve(PLAN_RESOLVE_REQUEST)
    runner.check("§3.3 verbatim: workspace = Client",
                 resolution.workspace.name == "Client")
    runner.check("§3.3 verbatim: filesystem scope = M:\\Client",
                 resolution.scope.filesystem_paths == ["M:\\Client"])
    runner.check("path match, confidence 1.0",
                 resolution.matched == "path" and resolution.confidence == 1.0)

    deep = engine.resolve("اشتغل على M:\\Client\\site\\index.html وخلّها حلوة")
    runner.check("deep path resolves to the longest workspace",
                 deep.workspace.name == "Site" and deep.matched == "path")
    runner.check("slash/case tolerant resolution",
                 engine.resolve("شغل على m:/client").workspace.name == "Client")
    runner.check("no false positive across workspaces",
                 engine.resolve("اشتغل على M:\\NEXUS").workspace.name
                 != "Client")
    runner.check("POSIX root resolution",
                 engine.resolve("افحص /home/user/AndroidProject/manifest").workspace
                 .name == "Android")
    runner.check("unregistered path falls through to default",
                 engine.resolve("اشتغل على C:\\Windows").matched == "default")
    runner.check("name mention matches the workspace",
                 engine.resolve("شغّل على مشروع Client اليوم").workspace.name
                 == "Client")
    resolution_name = engine.resolve("شغّل على Client اليوم")
    runner.check("name match confidence 0.8",
                 resolution_name.matched == "name"
                 and resolution_name.confidence == 0.8)
    resolution_project = engine.resolve("المطلوب ClientWebsite كاملة")
    runner.check("project label match (0.7)",
                 resolution_project.workspace.name == "Client"
                 and resolution_project.matched == "project"
                 and resolution_project.confidence == 0.7)
    fallback = engine.resolve("ماذا عن الطقس اليوم؟")
    runner.check("default fallback (0.3) → 'main'",
                 fallback.matched == "default" and fallback.confidence == 0.3
                 and fallback.workspace.name == "main")
    runner.check("path tokens extracted in order",
                 path_tokens("اشتغل على M:\\Client و M:\\NEXUS")
                 == ["M:\\Client", "M:\\NEXUS"])
    runner.check("resolution serializes (to_dict)",
                 set(resolution.to_dict()) == {
                     "workspace_id", "workspace_name", "matched",
                     "confidence", "scope", "request",
                 })


def section_d(runner: Runner, manager: WorkspaceManager, engine: ScopeEngine) -> None:
    """D — Cross-workspace Access (§3.4)."""
    runner.section = "D/§3.4"

    runner.check("keywords: authentication expands to auth/login/token",
                 "auth" in keywords_for("authentication")
                 and "login" in keywords_for("authentication"))
    runner.check("keywords: unknown part keeps the raw keyword",
                 keywords_for("fractal") == ("fractal",))
    runner.check("keywords: phrase mentioning a concept expands",
                 "jwt" in keywords_for("authentication flow"))

    listing = [
        "M:\\NEXUS\\src\\auth\\login.py",
        "M:\\NEXUS\\src\\api\\handler.py",
        "M:\\NEXUS\\docs\\AUTH-OVERVIEW.md",
        "M:\\NEXUS\\nexus\\core\\runtime.py",
    ]
    access = engine.request_cross_workspace(
        "Client", "NEXUS", "authentication", lister=lambda _root: listing
    )
    runner.check("access granted — never an absolute block", access.granted)
    carved = access.resolved_scope.filesystem_paths
    runner.check("carved scope contains only the requested part",
                 "M:\\NEXUS\\src\\auth\\login.py" in carved
                 and "M:\\NEXUS\\docs\\AUTH-OVERVIEW.md" in carved
                 and "M:\\NEXUS\\src\\api\\handler.py" not in carved
                 and "M:\\NEXUS\\nexus\\core\\runtime.py" not in carved)
    runner.check("carved scope never equals the whole workspace",
                 carved != ["M:\\NEXUS"] and len(carved) < len(listing))
    runner.check("audit record links source and target",
                 access.source_workspace_id == manager.get_by_name("Client").id
                 and access.target_workspace_id == manager.get_by_name("NEXUS").id
                 if manager.get_by_name("NEXUS") is not None
                 else False)
    runner.check("histories stay separate: unrelated sessions not carved",
                 access.resolved_scope.browser_sessions == [])
    runner.check("access record is logged",
                 len(engine.access_history()) == 1
                 and engine.access_history()[0].id == access.id)

    again = engine.request_cross_workspace(
        "Client", "NEXUS", "authentication", lister=lambda _root: listing
    )
    runner.check("repeated access still granted (no lockout)",
                 again.granted and len(engine.access_history()) == 2)

    pattern_access = engine.request_cross_workspace("Client", "NEXUS", "database")
    pattern_paths = pattern_access.resolved_scope.filesystem_paths
    runner.check("without a lister: scoped patterns, not the root",
                 pattern_paths != ["M:\\NEXUS"]
                 and all("**" in p for p in pattern_paths)
                 and any("db" in p.lower() for p in pattern_paths))

    ghost = engine.request_cross_workspace("Client", "Ghost", "authentication")
    runner.check("unregistered target: no grant, no exception (nonexistence ≠ block)",
                 not ghost.granted and ghost.resolved_scope.is_empty()
                 and "not registered" in ghost.reason)
    same = engine.request_cross_workspace("Client", "Client", "config")
    runner.check("same-workspace request still scoped and granted",
                 same.granted and same.source_workspace_id == same.target_workspace_id)

    record = access.to_dict()
    runner.check("access record serializes",
                 isinstance(record, dict) and record["granted"] is True
                 and isinstance(record["resolved_scope"], dict)
                 and "created_at" in record)
    runner.check("CrossWorkspaceAccess ids carry the cwa_ prefix",
                 access.id.startswith("cwa_"))


def section_e(runner: Runner) -> None:
    """E — Task Policy (§3.5)."""
    runner.section = "E/§3.5"

    policy = TaskPolicy.default()
    runner.check("nine §3.5 components, verbatim",
                 list(POLICY_COMPONENTS) == PLAN_POLICY_COMPONENTS
                 and all(hasattr(policy, name) for name in POLICY_COMPONENTS))
    runner.check("default autonomy is FULL (Full Control within Task Scope)",
                 policy.autonomy_level is AutonomyLevel.FULL)
    runner.check("autonomy is ordered OBSERVE < SUGGEST < ACT_CONFIRMED < FULL",
                 AutonomyLevel.OBSERVE < AutonomyLevel.SUGGEST
                 < AutonomyLevel.ACT_CONFIRMED < AutonomyLevel.FULL)
    runner.check("time defaults unlimited",
                 policy.time_policy.max_duration_seconds is None
                 and policy.time_policy.deadline is None)
    runner.check("network defaults: allow all, nothing blocked, online",
                 policy.network_policy.allowed_hosts == ["*"]
                 and policy.network_policy.blocked_hosts == []
                 and not policy.network_policy.offline)
    runner.check("tool defaults: allow all",
                 policy.tool_policy.allowed_tools == ["*"]
                 and policy.tool_policy.blocked_tools == []
                 and policy.tool_policy.confirm_tools == [])
    runner.check("workspace scope defaults cross-workspace allowed",
                 policy.workspace_scope.allow_cross_workspace is True)
    runner.check("app defaults: any application, launch allowed",
                 policy.app_scope.applications == ["*"]
                 and policy.app_scope.launch_allowed is True)
    runner.check("git defaults: all operations, main protected",
                 policy.git_policy.can_commit and policy.git_policy.can_push
                 and policy.git_policy.can_pull
                 and policy.git_policy.protected_branches == ["main"])
    runner.check("external AI defaults: allowed, any provider",
                 policy.external_ai_policy.allowed is True
                 and policy.external_ai_policy.providers == ["*"])
    runner.check("resource defaults: 3 parallel agents, unbounded memory",
                 policy.resource_policy.max_parallel_agents == 3
                 and policy.resource_policy.max_memory_mb is None)

    restricted = TaskPolicy.from_overrides({
        "autonomy_level": "SUGGEST",
        "network_policy.offline": True,
        "git_policy": {"can_push": "false"},
        "workspace_scope.allow_cross_workspace": False,
        "tool_policy.blocked_tools": ["format_c"],
        "resource_policy.max_parallel_agents": "5",
        "unknown_key": "ignored",
    })
    runner.check("dotted overrides: autonomy by name",
                 restricted.autonomy_level is AutonomyLevel.SUGGEST)
    runner.check("dotted overrides: network offline", restricted.network_policy.offline)
    runner.check("whole-component override with coercion",
                 restricted.git_policy.can_push is False)
    runner.check("dotted overrides: cross-workspace disabled",
                 restricted.workspace_scope.allow_cross_workspace is False)
    runner.check("dotted overrides: blocked tools list",
                 restricted.tool_policy.blocked_tools == ["format_c"])
    runner.check("string int coerced",
                 restricted.resource_policy.max_parallel_agents == 5)
    runner.check("autonomy accepts numeric forms",
                 TaskPolicy.from_overrides({"autonomy_level": "3"}).autonomy_level
                 is AutonomyLevel.ACT_CONFIRMED
                 and TaskPolicy.from_overrides(
                     {"autonomy_level": 4}
                 ).autonomy_level is AutonomyLevel.FULL)

    workspace = Workspace.create(
        name="P", path="M:\\P",
        settings={"policy": {"autonomy_level": "OBSERVE",
                             "network_policy": {"offline": True}}},
    )
    seeded = TaskPolicy.for_workspace(workspace)
    runner.check("for_workspace seeds from settings['policy']",
                 seeded.autonomy_level is AutonomyLevel.OBSERVE
                 and seeded.network_policy.offline)
    runner.check("workspace without policy → defaults",
                 TaskPolicy.for_workspace(
                     Workspace.create(name="Q", path="M:\\Q")
                 ).autonomy_level is AutonomyLevel.FULL)

    mutated = TaskPolicy.from_overrides({
        "autonomy_level": "ACT_CONFIRMED",
        "time_policy.max_duration_seconds": 3600,
        "network_policy.allowed_hosts": ["internal.local"],
        "tool_policy.confirm_tools": ["browser"],
        "workspace_scope.filesystem_paths": ["M:\\Client"],
        "app_scope.applications": ["VS Code"],
        "git_policy.protected_branches": ["main", "release"],
        "external_ai_policy.providers": ["openai"],
        "resource_policy.max_memory_mb": 512,
    })
    rebuilt = TaskPolicy.from_dict(mutated.to_dict())
    runner.check("to_dict/from_dict round-trip keeps all nine components",
                 rebuilt.autonomy_level is AutonomyLevel.ACT_CONFIRMED
                 and rebuilt.time_policy.max_duration_seconds == 3600
                 and rebuilt.network_policy.allowed_hosts == ["internal.local"]
                 and rebuilt.tool_policy.confirm_tools == ["browser"]
                 and rebuilt.workspace_scope.filesystem_paths == ["M:\\Client"]
                 and rebuilt.app_scope.applications == ["VS Code"]
                 and rebuilt.git_policy.protected_branches == ["main", "release"]
                 and rebuilt.external_ai_policy.providers == ["openai"]
                 and rebuilt.resource_policy.max_memory_mb == 512)


def section_f(runner: Runner, root: Path) -> None:
    """F — Policy Engine decisions + runtime integration + regression."""
    runner.section = "F/§3.1–§3.5"

    bus = EventBus()
    recorder = Recorder(bus)
    runtime = NexusRuntime.boot(root, bus=bus)
    manager = runtime.workspace_manager
    engine = runtime.policy_engine
    scope_engine = runtime.scope_engine

    runner.check("runtime wires workspace/scope/policy engines",
                 isinstance(manager, WorkspaceManager)
                 and isinstance(engine, PolicyEngine)
                 and isinstance(scope_engine, ScopeEngine))
    runner.check("system.started still published",
                 "system.started" in recorder.names)
    started = [e for e in bus.history_snapshot() if e.name == "system.started"]
    runner.check("boot payload reports phase ≥ 2 (Phase 2 wiring persists)",
                 started and started[-1].payload.get("phase", 0) >= 2)

    client_ws = manager.register(
        name="Client", path="M:\\Client", project="ClientWebsite",
        settings={"applications": ["VS Code", "Chrome"],
                  "tools": ["terminal", "git"],
                  "browser_sessions": ["browse-1"]},
    )
    manager.register(name="Other", path="M:\\Other")
    client_scope = scope_engine.resolve("اشتغل على M:\\Client").scope

    # ---- within scope: full control
    full = TaskPolicy.default()
    act = TaskPolicy.from_overrides({"autonomy_level": "ACT_CONFIRMED"})
    suggest = TaskPolicy.from_overrides({"autonomy_level": "SUGGEST"})
    observe = TaskPolicy.from_overrides({"autonomy_level": "OBSERVE"})

    def decide(action: PolicyAction, policy: TaskPolicy) -> object:
        return engine.decide(action, policy, task_scope=client_scope)

    read_app = PolicyAction(ActionType.READ, "M:\\Client\\app.py")
    write_app = PolicyAction(ActionType.WRITE, "M:\\Client\\app.py")
    delete_app = PolicyAction(ActionType.DELETE, "M:\\Client\\old.py")

    runner.check("READ in scope allowed at OBSERVE",
                 decide(read_app, observe).allowed)
    runner.check("WRITE in scope denied at OBSERVE",
                 not decide(write_app, observe).allowed)
    runner.check("WRITE in scope → confirm at SUGGEST",
                 decide(write_app, suggest).requires_confirmation)
    runner.check("WRITE in scope allowed at ACT_CONFIRMED",
                 decide(write_app, act).allowed
                 and not decide(write_app, act).requires_confirmation)
    runner.check("WRITE in scope allowed at FULL",
                 decide(write_app, full).allowed)
    runner.check("DELETE in scope → confirm at ACT_CONFIRMED (destructive)",
                 decide(delete_app, act).requires_confirmation)
    runner.check("DELETE in scope allowed at FULL",
                 decide(delete_app, full).allowed)

    # ---- outside scope: never an absolute wall (§3.4)
    read_other = PolicyAction(ActionType.READ, "M:\\Other\\note.txt")
    write_other = PolicyAction(ActionType.WRITE, "M:\\Other\\note.txt")
    d = decide(read_other, act)
    runner.check("cross-workspace READ allowed (Spec §21 flow)",
                 d.allowed and not d.requires_confirmation and not d.in_scope)
    d = decide(write_other, act)
    runner.check("cross-workspace WRITE → confirm at ACT_CONFIRMED",
                 d.allowed and d.requires_confirmation)
    d = decide(write_other, full)
    runner.check("cross-workspace WRITE allowed at FULL (scoped, audited)",
                 d.allowed and not d.requires_confirmation and not d.in_scope)
    no_cross = TaskPolicy.from_overrides(
        {"autonomy_level": "FULL", "workspace_scope.allow_cross_workspace": False}
    )
    d = decide(write_other, no_cross)
    runner.check("allow_cross_workspace=False → human approval, not a wall",
                 d.allowed and d.requires_confirmation)
    d = decide(read_other, no_cross)
    runner.check("reads never blocked even with cross disabled",
                 d.allowed and not d.requires_confirmation)
    d = decide(PolicyAction(ActionType.WRITE, "C:\\Temp\\scratch.txt"), act)
    runner.check("unregistered path WRITE → confirm at ACT_CONFIRMED",
                 d.allowed and d.requires_confirmation)

    # ---- explicit negative policies → deny
    offline = TaskPolicy.from_overrides({"network_policy.offline": True})
    d = engine.decide(PolicyAction(ActionType.NETWORK, "example.com"), offline)
    runner.check("offline network denied", not d.allowed and d.verdict == "deny")
    blocked_host = TaskPolicy.from_overrides(
        {"network_policy.blocked_hosts": ["evil.com"]}
    )
    d = engine.decide(PolicyAction(ActionType.NETWORK, "evil.com"), blocked_host)
    runner.check("blocked host denied", not d.allowed)
    d = engine.decide(PolicyAction(ActionType.NETWORK, "example.com"), full)
    runner.check("allowed host allowed at FULL",
                 d.allowed and d.verdict == "allow")
    strict_hosts = TaskPolicy.from_overrides(
        {"network_policy.allowed_hosts": ["internal.local"],
         "autonomy_level": "ACT_CONFIRMED"}
    )
    d = engine.decide(PolicyAction(ActionType.NETWORK, "example.com"), strict_hosts)
    runner.check("host outside allow-list → confirm at ACT_CONFIRMED",
                 d.requires_confirmation)
    d = engine.decide(PolicyAction(ActionType.NETWORK, "db.internal.local"),
                      strict_hosts)
    runner.check("host inside allow-list allowed",
                 d.allowed and not d.requires_confirmation)

    blocked_tool = TaskPolicy.from_overrides(
        {"tool_policy.blocked_tools": ["format_c"]}
    )
    d = engine.decide(PolicyAction(ActionType.TOOL, "format_c"), blocked_tool)
    runner.check("blocked tool denied", not d.allowed)
    confirm_tool = TaskPolicy.from_overrides(
        {"tool_policy.confirm_tools": ["browser"]}
    )
    d = engine.decide(PolicyAction(ActionType.TOOL, "browser"), confirm_tool)
    runner.check("confirm-first tool → confirmation", d.requires_confirmation)
    d = engine.decide(PolicyAction(ActionType.TOOL, "terminal"), full,
                      task_scope=client_scope)
    runner.check("allowed tool at FULL → allow", d.allowed)
    d = engine.decide(PolicyAction(ActionType.TOOL, "terminal"), suggest,
                      task_scope=client_scope)
    runner.check("tool is a mutation → confirm at SUGGEST",
                 d.requires_confirmation)

    no_push = TaskPolicy.from_overrides({"git_policy.can_push": False})
    d = engine.decide(PolicyAction(ActionType.GIT_PUSH, "feature/x"), no_push)
    runner.check("git push disabled → deny", not d.allowed)
    d = engine.decide(PolicyAction(ActionType.GIT_PUSH, "main"), full)
    runner.check("protected branch push → confirm even at FULL",
                 d.requires_confirmation and "protected" in d.reason)
    d = engine.decide(PolicyAction(ActionType.GIT_PUSH, "feature/x"), full)
    runner.check("normal branch push at FULL → allow", d.allowed)

    no_ai = TaskPolicy.from_overrides({"external_ai_policy.allowed": False})
    d = engine.decide(PolicyAction(ActionType.EXTERNAL_AI, "openai"), no_ai)
    runner.check("external AI disabled → deny", not d.allowed)
    local_ai = TaskPolicy.from_overrides(
        {"external_ai_policy.providers": ["local"],
         "autonomy_level": "ACT_CONFIRMED"}
    )
    d = engine.decide(PolicyAction(ActionType.EXTERNAL_AI, "openai"), local_ai)
    runner.check("unlisted AI provider → confirm at ACT_CONFIRMED",
                 d.requires_confirmation)

    no_launch = TaskPolicy.from_overrides({"app_scope.launch_allowed": False})
    d = engine.decide(PolicyAction(ActionType.APP_LAUNCH, "Chrome"), no_launch)
    runner.check("app launch disabled → deny", not d.allowed)
    vscode_only = TaskPolicy.from_overrides(
        {"app_scope.applications": ["VS Code"],
         "autonomy_level": "ACT_CONFIRMED"}
    )
    d = engine.decide(PolicyAction(ActionType.APP_LAUNCH, "Blender"), vscode_only)
    runner.check("unlisted application → confirm at ACT_CONFIRMED",
                 d.requires_confirmation)
    d = engine.decide(PolicyAction(ActionType.BROWSER_SESSION, "browse-1"), full,
                      task_scope=client_scope)
    runner.check("in-scope browser session allowed",
                 d.allowed and not d.requires_confirmation)
    d = engine.decide(PolicyAction(ActionType.BROWSER_SESSION, "browse-9"),
                      TaskPolicy.from_overrides({"autonomy_level": "ACT_CONFIRMED"}),
                      task_scope=client_scope)
    runner.check("out-of-scope browser session → confirm", d.requires_confirmation)

    verdicts = {decide(read_app, full).verdict,
                decide(write_app, suggest).verdict,
                decide(write_app, observe).verdict}
    runner.check("verdict vocabulary: allow / confirm / deny",
                 verdicts == {"allow", "confirm", "deny"})

    # ---- §2.3 bridge: Task.scope holds the canonical scope mapping
    conversation = runtime.session_manager.create_conversation(
        runtime.session_manager.create_user(display_name="Ops"),
        title="Phase 2",
    )
    task = runtime.session_manager.create_task(
        conversation,
        goal="Build the client website",
        prompt="ابنِ موقع العميل",
        scope=client_scope.to_scope_map(),
        workspace=client_ws.name,
    )
    runner.check("Task.scope carries the six §3.2 keys",
                 list(task.scope) == PLAN_SCOPE_DIMENSIONS)
    runner.check("Task.workspace names the resolved workspace",
                 task.workspace == "Client")
    runner.check("Scope.from_scope_map(Task.scope) round-trips",
                 Scope.from_scope_map(task.scope).to_scope_map()
                 == task.scope)

    # ---- persistence across restarts + shutdown symmetry
    runner.check("workspace registry persisted under the runtime root",
                 (root / "workspaces" / "workspaces.json").is_file())
    runtime.shutdown()
    runtime2 = NexusRuntime.boot(root)
    runner.check("registry reloads after NEXUS restart",
                 runtime2.workspace_manager.get_by_name("Client") is not None
                 and runtime2.workspace_manager.get_by_name("Other") is not None)
    resolution2 = runtime2.scope_engine.resolve("اشتغل على M:\\Client")
    runner.check("scope resolution works after restart",
                 resolution2.workspace.name == "Client")
    runtime2.shutdown()

    # ---- Phase 1 regression: the §2.6 harness must stay 98/98
    phase01 = subprocess.run(
        [sys.executable,
         str(REPO_ROOT / "tests" / "phase01" / "verify_exit_criteria.py")],
        capture_output=True,
        text=True,
        timeout=600,
    )
    runner.check("phase 1 harness still green (98/98)",
                 phase01.returncode == 0 and "98/98" in phase01.stdout,
                 detail=phase01.stdout.strip().splitlines()[-2]
                 if phase01.stdout.strip() else "no output")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="runtime root (default: isolated temp directory)",
    )
    args = parser.parse_args()

    runner = Runner()
    temp_base: str | None = None
    if args.root is None:
        temp_base = tempfile.mkdtemp(prefix="nexus-phase2-")
        base = Path(temp_base)
    else:
        base = Path(args.root).absolute()

    print("NEXUS Phase 2 — verification harness (Final Build Plan §3)")
    print(f"workspace base: {base}")

    try:
        manager = section_a(runner, base)
        section_b(runner, manager)
        engine = ScopeEngine(manager)
        section_c(runner, manager, engine)
        section_d(runner, manager, engine)
        section_e(runner)
        section_f(runner, base)
    finally:
        if temp_base is not None:
            shutil.rmtree(temp_base, ignore_errors=True)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
