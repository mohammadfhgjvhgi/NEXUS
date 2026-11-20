"""Runtime configuration & lifecycle (Final Build Plan §2.1, §3, §4, §5, §6).

:class:`NexusRuntime` is one running NEXUS instance: it resolves paths,
loads the typed configuration, owns the Event Bus and wires the session
manager, task engine and task repository (Phase 1, §2), the workspace
manager, scope engine and policy engine (Phase 2, §3), the resource
manager with its hardware scanner (Phase 3, §4), the Model Manager of
the Local Model Runtime (Phase 4, §5) **plus** the Agent Runtime
(Phase 5, §6).

Phase 5 notes:

* the §6.4 Agent Registry persists under ``NexusPaths.data``
  (``agents.registry.json``) and reloads on every boot — the roster
  is open, the §6.3 master record is seeded idempotently (first
  boot only) and can never be unregistered;
* the §6.5 communicator writes its optional per-task JSONL
  transcript next to the task record (``tasks/<id>.messages.jsonl``)
  when ``agents.message_log_enabled``;
* ``agents.master_agent_enabled = false`` leaves the runtime
  loop-capable but master-less (``runtime.master_agent is None``) —
  callers drive §6.2 loops directly;
* agent slots honor ``agents.max_parallel`` through the Phase-3
  ResourceManager (registered while working, released at teardown);
* shutdown releases every §6.6 ownership entry before unloading
  models — nothing is left held.

Phase 4 notes:

* the model registry persists under ``NexusPaths.models``
  (``models.registry.json``) — the §5.2 Model Registry;
* the first boot seeds the §5.6 MiMo Edge pool (the user's measured
  baselines, Spec §88) **once** — the pool is not fixed and every
  record can be dropped or replaced;
* the default provider is the §5.3 llama.cpp adapter; llama-server
  processes only start on an explicit ``load`` (nothing spawns at
  boot), and a missing binary fails that load — never the boot;
* shutdown unloads every resident model (provider ``close`` +
  ResourceManager release) before closing the repository;
* only the four §2.2 model events are published — the 28-event
  registry stays authoritative and binding.

Phase 3 notes:

* the hardware profile is **system data** persisted under
  ``NexusPaths.data`` (``hardware_profile.json``) — never model
  memory (Plan §4.2);
* boot only *loads* a persisted profile — scanning is explicit
  (``runtime.resource_manager.refresh_profile()``) so boot stays
  fast and the Phase 1/2 behavior is untouched;
* the resource component publishes no events of its own — the §2.2
  registry (28 canonical events) stays authoritative.

Boot / shutdown implement the §2.6 vocabulary:

* ``NexusRuntime.boot(root)``  → resolve + create dirs, load config,
  publish ``system.started``.
* ``runtime.shutdown()``       → close the repository. There is
  deliberately **no** ``system.stopped`` broadcast: the §2.2 registry of
  28 canonical events is authoritative and inventing names is forbidden;
  shutdown is logged instead.

The exit-criteria flow (create → save → close → open → load → continue)
is exactly: ``boot`` → work → ``save_task`` → ``shutdown`` → drop the
object → ``boot`` again → ``load_task``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from ...agents import (
    AgentCommunicator,
    AgentRegistry,
    MasterAgent,
    OwnershipManager,
)
from ...events import EventBus, EventName
from ...harness import (
    CheckpointStore,
    Durability,
    GoalStore,
    Harness,
    HarnessHooks,
    RuleSet,
    SessionTracker,
    SkillLibrary,
)
from ...models import LlamaCppProvider, ModelManager, ModelProvider
from ...resources import HardwareScanner, ResourceBudgets, ResourceManager
from ..engine.machine import TaskEngine
from ..persistence import TaskRepository, TaskSummary
from ..policy import PolicyEngine
from ..policy.models import TaskPolicy
from ..scope import ScopeEngine
from ..session import SessionManager
from ..session.models import Task
from ..workspace import WorkspaceManager
from .loader import load_config
from .paths import NexusPaths, resolve_paths
from .schema import NexusConfig

logger = logging.getLogger("nexus.core")


class NexusRuntime:
    """One running NEXUS instance (Plan §2.1 runtime configuration)."""

    def __init__(
        self,
        *,
        paths: NexusPaths,
        config: NexusConfig,
        bus: EventBus,
        hardware_scanner: HardwareScanner | None = None,
        model_provider: ModelProvider | None = None,
    ) -> None:
        self._paths = paths
        self._config = config
        self._bus = bus
        self._session_manager = SessionManager(bus)
        self._engine = TaskEngine(bus)
        self._repository = TaskRepository(paths.tasks)
        # Phase 2 (Plan §3): workspace registry + scope + policy
        self._workspace_manager = WorkspaceManager(
            paths.workspaces,
            default_workspace=config.workspaces.default_workspace,
        )
        self._scope_engine = ScopeEngine(self._workspace_manager)
        self._policy_engine = PolicyEngine(self._workspace_manager)
        # Phase 3 (Plan §4): hardware intelligence + resource manager.
        # agents.max_parallel (§2.1) is honored as the agent budget; all
        # other budgets default from the hardware profile (system data).
        self._resource_manager = ResourceManager(
            paths.data,
            scanner=hardware_scanner,
            budgets=ResourceBudgets(max_agents=config.agents.max_parallel),
        )
        # Phase 4 (Plan §5): the Local Model Runtime — the §5.4 Model
        # Manager over the §5.2 registry, the §5.7 router and the §5.3
        # llama.cpp adapter (llama-server starts only on explicit load).
        # ``model_provider`` injects an alternative backend (tests,
        # simulated runs) — the manager itself never knows which.
        provider = model_provider if model_provider is not None else (
            LlamaCppProvider(
                binary=config.models.llama_server,
                host=config.models.llama_host,
                port=config.models.llama_port,
                gpu_layers=config.models.gpu_layers,
                threads=config.models.threads,
                context_size=config.models.context_size,
                models_dir=str(paths.models),
            )
        )
        self._model_manager = ModelManager.from_config(
            paths.models,
            provider=provider,
            resources=self._resource_manager,
            bus=bus,
            keep_warm_seconds=config.models.keep_warm_seconds,
        )
        # Phase 5 (Plan §6): the Agent Runtime — §6.4 registry (atomic,
        # reloaded on boot, master seeded once), §6.5 communicator
        # (mailboxes + optional per-task transcript), §6.6 ownership
        # (in-process coordination), and the §6.3 Master Agent wiring
        # the task engine to the loops (disabled → None).
        self._agent_registry = AgentRegistry(paths.data)
        self._communicator = AgentCommunicator(
            tasks_dir=paths.tasks,
            persist=config.agents.message_log_enabled,
        )
        self._ownership = OwnershipManager()
        # Phase 6 (Plan §7 / Spec §41): the Harness — skills + rules
        # loaded from <root>/skills and <root>/rules (the §7.1 ECC
        # pattern), the 8-point hook registry (§7.1/§7.2), the §7.2
        # session ledger, the §7.3 checkpoint store (DISK durability,
        # event-driven on the task lifecycle) and the §7.4 goal
        # ledger. ``harness_enabled = false`` leaves every component
        # unwired (None) — the Phase-5 behavior, byte for byte.
        # Wired *before* the master: the §6.3 agent takes the harness
        # as an injected collaborator (§0.4 seams).
        if config.agents.harness_enabled:
            self._skill_library = SkillLibrary.load(paths.root / "skills")
            self._rule_set = RuleSet.load(paths.root / "rules")
            self._goal_store = GoalStore(paths.data)
            self._hooks = HarnessHooks(strict=config.agents.hooks_strict)
            self._hooks.bind_bus(bus)
            self._session_tracker = SessionTracker(paths.data)
            self._checkpoint_store = CheckpointStore(
                paths.checkpoints,
                mode=Durability.DISK,
                retention=config.agents.checkpoint_retention,
            )
            self._checkpoint_store.bind_bus(bus)
            self._harness = Harness(
                skills=self._skill_library,
                rules=self._rule_set,
                goals=self._goal_store,
                hooks=self._hooks,
            )
        else:
            self._skill_library = None
            self._rule_set = None
            self._goal_store = None
            self._hooks = None
            self._session_tracker = None
            self._checkpoint_store = None
            self._harness = None
        # Phase 7 (Plan §8): the Tool System — the §8.1 registry, the
        # §8.2 router (behind the §6.2 ToolSink seam, the Phase-6
        # pre_tool_call veto still in front) and the §8.4/§8.5 MCP
        # interop (official SDK, per-server honest failure — a
        # broken server never breaks the boot). ``tools.native_enabled =
        # false`` + ``tools.mcp_enabled = false`` leave everything
        # unwired (None) — the Phase-6 behavior, byte for byte.
        self._tool_registry = None
        self._tool_router = None
        self._mcp_adapter = None
        self._tool_sink = None
        # Phase 8 (Plan §9): the Windows Computer Runtime — the §9.1
        # façade (eight domains, thin router clients) + the §9.5
        # fallback hierarchy. ``tools.computer_enabled = false`` leaves
        # it unwired (None) — the Phase-7 behavior, byte for byte.
        self._computer_runtime = None
        # Phase 9 (Plan §10): the Window Manager — §10.1 registry ·
        # §10.2 ownership · §10.3 arbitration (installed as a
        # pre_tool_call veto when the harness runs) · §10.4 monitors
        # · §10.5 overlay, composed over the §9.1 Computer API.
        # ``tools.windows_enabled = false`` leaves it unwired (None)
        # — the Phase-8 behavior, byte for byte.
        self._window_manager = None
        # Phase 10 (Plan §11): the Browser Runtime — the §11.1
        # Playwright record (13th, additive) + the façade + the
        # §9.5 dom_a11y layer over the §8.2 router. Engine defaults
        # (channel ladder · headless) injected before any first use.
        # ``tools.browser_enabled = false`` leaves it unwired — the
        # Phase-9 behavior, byte for byte.
        self._browser_runtime = None
        # Phase 11 (Plan §12): the Vision Runtime — the §12 ``vision``
        # record (14th, additive) + the façade + the §9.5 vision rung
        # over the §12.2 ModelVisionProvider (the Phase 4 Model
        # Runtime behind the §5.7 router) + the §12.5 OCR preference.
        # ``tools.vision_enabled = false`` leaves it unwired — the
        # Phase-10 behavior, byte for byte.
        self._vision_runtime = None
        if config.tools.native_enabled or config.tools.mcp_enabled:
            # Imported at wiring time (not module level): the tool
            # system imports nexus.core.policy — a module-level import
            # here would close a cycle (core.config → tools → core).
            from ...tools import RoutedToolSink, build_tool_system
            from ...tools.mcp import load_mcp_servers

            mcp_servers = (
                load_mcp_servers(paths.config / "tools" / "mcp.toml")
                if config.tools.mcp_enabled
                else ()
            )
            default_workspace = self._workspace_manager.find(
                config.workspaces.default_workspace
            )
            workspace_root = (
                Path(default_workspace.path) if default_workspace is not None else None
            )
            default_policy = (
                TaskPolicy.for_workspace(default_workspace)
                if default_workspace is not None
                else TaskPolicy.default()
            )
            self._tool_registry, self._tool_router, self._mcp_adapter, _report = (
                build_tool_system(
                    native=config.tools.native_enabled,
                    computer=config.tools.computer_enabled,
                    browser=config.tools.browser_enabled,
                    vision=config.tools.vision_enabled,
                    workspace_root=workspace_root,
                    mcp_servers=mcp_servers,
                    mcp_config_file=(paths.config / "tools" / "mcp.toml")
                    if config.tools.mcp_enabled
                    else None,
                    policy_engine=self._policy_engine,
                    resources=self._resource_manager,
                    bus=bus,
                    confirm_danger_above=config.tools.confirm_danger_above,
                    allow_network=config.tools.allow_network,
                )
            )
            self._tool_sink = RoutedToolSink(
                self._tool_router,
                policy=default_policy,
                workspace_id=(
                    default_workspace.id if default_workspace is not None else None
                ),
            )
            if config.tools.computer_enabled and self._tool_router is not None:
                # Imported at wiring time (§0.4) — nexus.computer pulls
                # the tool pack, a module-level import would close a
                # cycle (core.config → computer → tools → core).
                from ...computer import build_computer_runtime

                self._computer_runtime = build_computer_runtime(
                    self._tool_router,
                    policy=default_policy,
                    workspace_id=(
                        default_workspace.id if default_workspace is not None else None
                    ),
                )
                if config.tools.windows_enabled and self._computer_runtime is not None:
                    # Imported at wiring time (§0.4): nexus.windows pulls
                    # the computer package, a module-level import would
                    # close a cycle (core.config → windows → computer →
                    # tools → core).
                    from ...windows import build_window_manager

                    self._window_manager = build_window_manager(
                        self._computer_runtime, bus=bus
                    )
                    if self._hooks is not None:
                        self._hooks.register(
                            "pre_tool_call", self._window_manager.hook()
                        )
                if config.tools.browser_enabled and self._tool_router is not None:
                    # Imported at wiring time (§0.4) — same cycle rule.
                    from ...browser import BrowserRuntime, set_engine_defaults

                    set_engine_defaults(
                        channel=config.tools.browser_channel,
                        headless=config.tools.browser_headless,
                        data_root=paths.data,
                    )
                    self._browser_runtime = BrowserRuntime(
                        self._tool_router,
                        policy=default_policy,
                        workspace_id=(
                            default_workspace.id if default_workspace is not None else None
                        ),
                    )
                    if self._computer_runtime is not None:
                        # the §9.5 chain gains its dom_a11y rung
                        from ...browser import BrowserDomLayer

                        self._computer_runtime.chain.register(
                            BrowserDomLayer(self._tool_router)
                        )
                if config.tools.vision_enabled and self._tool_router is not None:
                    # Imported at wiring time (§0.4) — nexus.vision
                    # pulls the tool pack; a module-level import would
                    # close a cycle (core.config → vision → tools).
                    from ...vision import (
                        ModelVisionProvider,
                        VisionLayer,
                        VisionRuntime,
                        provider_state,
                    )

                    # the §12.2 provider over the live Model Runtime
                    # (None manager → the honest stub: capture works,
                    # inference refuses with a reason)
                    provider = ModelVisionProvider(self._model_manager)
                    provider_state.set_provider(provider)
                    provider_state.set_ocr_preference(
                        config.tools.vision_ocr_engine
                    )
                    self._vision_runtime = VisionRuntime(
                        self._tool_router,
                        policy=default_policy,
                        workspace_id=(
                            default_workspace.id if default_workspace is not None else None
                        ),
                    )
                    if self._computer_runtime is not None:
                        # the §9.5 chain gains its vision rung (fourth
                        # of five — the Plan §12 seam)
                        self._computer_runtime.chain.register(
                            VisionLayer(self._computer_runtime, provider)
                        )
        self._master_agent = (
            MasterAgent(
                registry=self._agent_registry,
                communicator=self._communicator,
                ownership=self._ownership,
                model_manager=self._model_manager,
                engine=self._engine,
                bus=bus,
                resources=self._resource_manager,
                tools=self._tool_sink,
                max_parallel=config.agents.max_parallel,
                repair_limit=config.agents.master_repair_limit,
                loop_max_turns=config.agents.loop_max_turns,
                harness=self._harness,
            )
            if config.agents.master_agent_enabled
            else None
        )
        if config.agents.master_agent_enabled:
            self._agent_registry.seed_master()

    # ----------------------------------------------------------------- boot

    @classmethod
    def boot(
        cls,
        root: str | Path | None = None,
        *,
        env: Mapping[str, str] | None = None,
        bus: EventBus | None = None,
        strict_events: bool = False,
        hardware_scanner: HardwareScanner | None = None,
        model_provider: ModelProvider | None = None,
    ) -> NexusRuntime:
        """Start NEXUS: paths + config + event bus; publishes
        ``system.started``."""
        paths = resolve_paths(root, env=env, create=True)
        config = load_config(paths=paths, env=env)
        event_bus = bus if bus is not None else EventBus(strict_names=strict_events)
        logging.getLogger("nexus").setLevel(config.system.log_level.upper())
        runtime = cls(
            paths=paths, config=config, bus=event_bus,
            hardware_scanner=hardware_scanner,
            model_provider=model_provider,
        )
        event_bus.publish(
            EventName.SYSTEM_STARTED,
            payload={
                "version": config.system.version,
                "phase": 7,
                "language": config.system.language,
                "root": str(paths.root),
            },
            source="nexus.runtime",
        )
        logger.info("NEXUS runtime booted (root=%s)", paths.root)
        return runtime

    # -------------------------------------------------------------- accessors

    @property
    def paths(self) -> NexusPaths:
        return self._paths

    @property
    def config(self) -> NexusConfig:
        return self._config

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    @property
    def engine(self) -> TaskEngine:
        return self._engine

    @property
    def repository(self) -> TaskRepository:
        return self._repository

    @property
    def workspace_manager(self) -> WorkspaceManager:
        """Phase 2 (§3.1): the persistent workspace registry."""
        return self._workspace_manager

    @property
    def scope_engine(self) -> ScopeEngine:
        """Phase 2 (§3.2–§3.4): scope resolution + cross-workspace access."""
        return self._scope_engine

    @property
    def policy_engine(self) -> PolicyEngine:
        """Phase 2 (§3.5): task policy decisions."""
        return self._policy_engine

    @property
    def resource_manager(self) -> ResourceManager:
        """Phase 3 (§4.4): hardware profile + the eight tracked
        resources. ``refresh_profile()`` scans → diffs → persists."""
        return self._resource_manager

    @property
    def model_manager(self) -> ModelManager:
        """Phase 4 (§5): the Local Model Runtime — §5.2 registry, §5.3
        adapter, §5.4 dynamic loading, §5.5 benchmarks, §5.7 router."""
        return self._model_manager

    @property
    def agent_registry(self) -> AgentRegistry:
        """Phase 5 (§6.4): the persistent Agent Registry (open roster)."""
        return self._agent_registry

    @property
    def communicator(self) -> AgentCommunicator:
        """Phase 5 (§6.5): the structured-message routing hub."""
        return self._communicator

    @property
    def ownership(self) -> OwnershipManager:
        """Phase 5 (§6.6): the resource→owner coordination registry."""
        return self._ownership

    @property
    def master_agent(self) -> MasterAgent | None:
        """Phase 5 (§6.3): the Master Agent — ``None`` when disabled
        by ``agents.master_agent_enabled = false``."""
        return self._master_agent

    @property
    def harness(self) -> Harness | None:
        """Phase 6 (§41): the harness assembler — ``None`` when
        disabled by ``agents.harness_enabled = false``."""
        return self._harness

    @property
    def skill_library(self) -> SkillLibrary | None:
        """Phase 6 (§7.1): the loaded skill library (ECC pattern)."""
        return self._skill_library

    @property
    def rule_set(self) -> RuleSet | None:
        """Phase 6 (§7.1): the compiled rule set (ECC pattern)."""
        return self._rule_set

    @property
    def hooks(self) -> HarnessHooks | None:
        """Phase 6 (§7.1/§7.2): the 8-point hook registry."""
        return self._hooks

    @property
    def session_tracker(self) -> SessionTracker | None:
        """Phase 6 (§7.2): the agent session ledger (Cline pattern)."""
        return self._session_tracker

    @property
    def checkpoint_store(self) -> CheckpointStore | None:
        """Phase 6 (§7.3): the task checkpoint store (LangGraph
        pattern) — event-driven on the task lifecycle."""
        return self._checkpoint_store

    @property
    def goal_store(self) -> GoalStore | None:
        """Phase 6 (§7.4): the persistent goal ledger (Prime pattern)."""
        return self._goal_store

    @property
    def tool_registry(self):
        """Phase 7 (§8.1): the Tool Registry — ``None`` when the tool
        system is disabled (``tools.*_enabled = false``)."""
        return self._tool_registry

    @property
    def tool_router(self):
        """Phase 7 (§8.2): the Tool Router (seven-stage pipeline)."""
        return self._tool_router

    @property
    def mcp_adapter(self):
        """Phase 7 (§8.4): the MCP interop adapter (official SDK)."""
        return self._mcp_adapter

    @property
    def tool_sink(self):
        """Phase 7 (§8.2): the §6.2 seam the Agent Loop dispatches
        through — the Master Agent receives it at construction."""
        return self._tool_sink

    @property
    def computer_runtime(self):
        """Phase 8 (§9.1): the Windows Computer Runtime — ``None``
        when ``tools.computer_enabled = false``."""
        return self._computer_runtime

    @property
    def window_manager(self):
        """Phase 9 (§10): the Window Manager — ``None`` when
        ``tools.windows_enabled = false`` or the Computer Runtime is
        off (§10 composes over §9.1)."""
        return self._window_manager

    @property
    def browser_runtime(self):
        """Phase 10 (§11): the Browser Runtime façade — ``None`` when
        ``tools.browser_enabled = false``."""
        return self._browser_runtime

    @property
    def vision_runtime(self):
        """Phase 11 (§12): the Vision Runtime façade — ``None`` when
        ``tools.vision_enabled = false``."""
        return self._vision_runtime

    # ------------------------------------------------------- persistence API

    def save_task(self, task: Task) -> Path:
        """Persist a task (explicit — §2.6: tasks must be savable)."""
        return self._repository.save(task)

    def load_task(self, task_id: str) -> Task:
        """Load a task and register it for continuation (§2.6)."""
        task = self._repository.load(task_id)
        self._session_manager.register_task(task)
        return task

    def list_tasks(self) -> list[TaskSummary]:
        return self._repository.list_summaries()

    # -------------------------------------------------------------- shutdown

    def shutdown(self) -> None:
        """Close NEXUS (§2.6). Atomic writes mean nothing to flush; the
        §6.6 ownership entries are released first (audit-logged), then
        the browser engine shuts down (Phase 10 — every context
        closed, the driver stopped), then every MCP session is closed
        (Phase 7 — stdio children get a clean exit), then every
        resident model is unloaded (provider close + budget
        release), then the repository is closed for symmetry and the
        shutdown is logged (no invented event name — §2.2 registry
        is authoritative)."""
        self._ownership.clear()
        if self._window_manager is not None:
            self._window_manager.shutdown()
        if self._browser_runtime is not None:
            from ...browser import get_engine

            get_engine().shutdown()
        if self._vision_runtime is not None:
            # Phase 11: unwire the process-wide §12.2 provider so a
            # re-boot re-injects cleanly (the stub refuses honestly)
            from ...vision import provider_state

            provider_state.reset()
        if self._mcp_adapter is not None:
            self._mcp_adapter.shutdown()
        self._model_manager.shutdown()
        self._repository.close()
        self._workspace_manager.close()
        logger.info("NEXUS runtime shut down (root=%s)", self._paths.root)
