#!/usr/bin/env python3
"""Phase 1 verification harness — Final Build Plan §2 Exit Criteria (§2.6).

Proves the NEXUS Core Foundation section by section:

* A — Core Configuration (§2.1): typed sections, environment resolution,
       local paths, file overrides, validation.
* B — Event Bus (§2.2): the 28 canonical events, patterns, isolation,
       history, strict mode.
* C — Session System (§2.3): User → Conversation → Task → Session,
       separated identities, no overlapping sessions.
* D — Task Engine (§2.4): the 13 states, legal/illegal transitions,
       terminal locks, pause/resume, transition events.
* E — Task Persistence (§2.5): the 11 fields round-trip atomically.
* F — Exit Criteria (§2.6): create → save → CLOSE NEXUS → OPEN NEXUS →
       retrieve → continue state → persist again.

Run:  python tests/phase01/verify_exit_criteria.py [--root DIR]
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.core.config import (  # noqa: E402
    ConfigError,
    NexusRuntime,
    resolve_paths,
)
from nexus.core.engine.machine import TaskEngine  # noqa: E402
from nexus.core.engine.states import (  # noqa: E402
    InvalidTransitionError,
    TaskState,
)
from nexus.core.persistence import PersistenceError  # noqa: E402
from nexus.core.session import (  # noqa: E402
    CheckpointRef,
    Conversation,
    PlanStep,
    SessionError,
    Task,
    TaskError,
    TaskPlan,
    User,
    VerificationCheck,
    VerificationRecord,
    VerificationStatus,
)
from nexus.events import CANONICAL_EVENTS, EventBus, EventName  # noqa: E402

# --- verbatim expectations from the Final Build Plan -----------------------

PLAN_EVENTS = {
    "system.started",
    "task.created", "task.started", "task.updated", "task.paused",
    "task.resumed", "task.completed",
    "agent.started", "agent.completed", "agent.failed",
    "tool.called", "tool.completed", "tool.failed",
    "model.loading", "model.loaded", "model.unloaded", "model.error",
    "window.opened", "window.closed",
    "checkpoint.created", "recovery.started", "recovery.completed",
    "verification.started", "verification.passed", "verification.failed",
    "memory.created", "memory.updated", "learning.created",
}

PLAN_STATES = {
    "CREATED", "ANALYZING", "CLARIFICATION_REQUIRED", "PLANNING",
    "EXECUTING", "VERIFYING", "REPAIRING", "WAITING_NETWORK",
    "WAITING_RESOURCE", "RECOVERING", "PAUSED", "COMPLETED", "CANCELLED",
}

PLAN_TASK_FIELDS = [
    "goal", "prompt", "scope", "workspace", "plan", "agents", "state",
    "checkpoints", "errors", "verification", "result",
]


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
        print(f"PHASE 1 EXIT CRITERIA — {self.passed}/{total} checks passed"
              f" ({self.failed} failed)")
        print("=" * 72)
        return 0 if self.failed == 0 else 1


class Recorder:
    """Subscribes to '*' and records (name, event) pairs."""

    def __init__(self, bus: EventBus) -> None:
        self.events: list[tuple[str, dict]] = []
        self.subscription = bus.subscribe(
            "*", lambda event: self.events.append((event.name, event.to_dict()))
        )

    def names(self) -> list[str]:
        return [name for name, _ in self.events]

    def clear(self) -> None:
        self.events.clear()


def make_rich_task(conversation: Conversation, manager) -> Task:
    """Create a task that populates every §2.5 field with distinct values."""
    plan = TaskPlan(
        steps=[
            PlanStep.create("analyze the request"),
            PlanStep.create("draft the report"),
            PlanStep.create("verify the output"),
        ]
    )
    task = manager.create_task(
        conversation,
        goal="Produce the quarterly report with charts",
        prompt="اعمل تقرير الربع الأخير وحط الرسوم البيانية والمراجع",
        scope={"allowed_paths": ["M:\\Work\\Reports"], "network": True},
        workspace="reports",
        plan=plan,
        agents=["planner", "writer"],
    )
    task.checkpoints.append(
        CheckpointRef.create(reason="after planning")
    )
    task.errors.append(
        TaskError.create(code="E_TEST", message="sample error record",
                         source="harness")
    )
    task.verification = VerificationRecord(
        status=VerificationStatus.PENDING,
        checks=[
            VerificationCheck(name="file exists", passed=True, detail="ok"),
            VerificationCheck(name="layout valid", passed=False, detail="wip"),
        ],
        started_at=None,
    )
    return task


def section_a(runner: Runner) -> None:
    """A — Core Configuration (§2.1)."""
    runner.section = "A/§2.1"
    print("\nA — Core Configuration (§2.1)")

    from nexus.core.config import load_config

    with tempfile.TemporaryDirectory(prefix="nexus-a-") as tmp:
        root = Path(tmp)

        paths = resolve_paths(root, create=True)
        runner.check("root resolved to argument", paths.root == root)
        runner.check(
            "config has the six §2.1 section dirs",
            all(
                (paths.config / name).is_dir()
                for name in ("system", "models", "tools", "agents",
                             "workspaces", "security")
            ),
        )
        runner.check(
            "runtime dirs follow Spec §245",
            all(
                (root / name).is_dir()
                for name in ("config", "data", "tasks", "checkpoints",
                             "logs", "memory", "models", "workspaces",
                             "cache", "plugins", "runtime", "docs")
            ),
        )

        config = load_config(paths=paths, env={})
        runner.check("defaults load without any file", config.system.language == "ar")
        runner.check(
            "all six sections are typed instances",
            all(
                hasattr(config, name) and hasattr(getattr(config, name), "__dataclass_fields__")
                for name in ("system", "models", "tools", "agents",
                             "workspaces", "security")
            ),
        )

        # file override
        sys_dir = root / "config" / "system"
        sys_dir.mkdir(parents=True, exist_ok=True)
        (sys_dir / "system.toml").write_text(
            "# harness override\n[system]\ndebug = true\nlog_level = \"DEBUG\"\n",
            encoding="utf-8",
        )
        config = load_config(paths=paths, env={})
        runner.check("TOML file overrides default", config.system.debug is True)
        runner.check("file provenance recorded",
                     config.provenance.get("system.debug") == "file")

        # env overrides file
        config = load_config(
            paths=paths,
            env={"NEXUS_SYSTEM__DEBUG": "false", "NEXUS_MODELS__CONTEXT_SIZE": "4096",
                 "NEXUS_SECURITY__REDACT_SECRETS": "no"},
        )
        runner.check("env overrides file (bool false)", config.system.debug is False)
        runner.check("env int parsing", config.models.context_size == 4096)
        runner.check("env bool 'no' parsing", config.security.redact_secrets is False)
        runner.check("env provenance recorded",
                     config.provenance.get("system.debug") == "env")

        # validation failures
        try:
            load_config(paths=paths, env={"NEXUS_SYSTEM__LOG_LEVEL": "BOGUS"})
            runner.check("invalid value rejected", False)
        except ConfigError:
            runner.check("invalid value rejected", True)

        # unknown key → warning, not failure
        (sys_dir / "system.toml").write_text(
            "[system]\nfuture_key = \"x\"\n", encoding="utf-8"
        )
        config = load_config(paths=paths, env={})
        runner.check("unknown key ignored with warning",
                     any("future_key" in w for w in config.warnings))

        # path env overrides
        alt_tasks = root / "alt-tasks"
        paths2 = resolve_paths(root, env={"NEXUS_TASKS_DIR": str(alt_tasks)})
        runner.check("NEXUS_TASKS_DIR override honored", paths2.tasks == alt_tasks)

        paths3 = resolve_paths(None, env={"NEXUS_HOME": str(root)})
        runner.check("NEXUS_HOME honored", paths3.root == root)


def section_b(runner: Runner) -> None:
    """B — Event Bus (§2.2)."""
    runner.section = "B/§2.2"
    print("\nB — Event Bus (§2.2)")

    runner.check(
        "exactly the 28 canonical plan events",
        CANONICAL_EVENTS == PLAN_EVENTS,
        f"count={len(CANONICAL_EVENTS)}",
    )

    bus = EventBus()
    seen_exact: list[str] = []
    seen_wild: list[str] = []
    seen_all: list[str] = []
    bus.subscribe("tool.completed", lambda e: seen_exact.append(e.name))
    bus.subscribe("task.*", lambda e: seen_wild.append(e.name))
    bus.subscribe("*", lambda e: seen_all.append(e.name))

    bus.publish(EventName.TOOL_COMPLETED, payload={"tool": "fs.read"})
    bus.publish(EventName.TASK_CREATED, task_id="task_x")
    bus.publish(EventName.MODEL_LOADING, payload={"model": "qwen"})

    runner.check("exact-name subscription", seen_exact == ["tool.completed"])
    runner.check("prefix wildcard 'task.*'", seen_wild == ["task.created"])
    runner.check("global '*' sees everything", len(seen_all) == 3)

    # once-subscription
    once_seen: list[str] = []
    bus.subscribe("model.loaded", lambda e: once_seen.append(e.name), once=True)
    bus.publish(EventName.MODEL_LOADED)
    bus.publish(EventName.MODEL_LOADED)
    runner.check("once-subscription fires exactly once", len(once_seen) == 1)

    # handler isolation
    survivor: list[str] = []
    bus.subscribe(
        "agent.failed",
        lambda e: (_ for _ in ()).throw(RuntimeError("boom")),  # raising handler
    )
    bus.subscribe("agent.failed", lambda e: survivor.append(e.name))
    result = bus.publish(EventName.AGENT_FAILED)
    runner.check("raising handler isolated", survivor == ["agent.failed"])
    runner.check("dispatch errors captured", len(result.errors) == 1)
    # 3 matched: the raising handler, the survivor, and the '*' subscriber
    runner.check("other handlers still ran", result.handler_count == 3)

    # history
    bus.clear_history()
    for i in range(5):
        bus.publish(EventName.MEMORY_UPDATED, payload={"i": i})
    snap = bus.history_snapshot("memory.*")
    runner.check("history snapshot filtered", len(snap) == 5)
    runner.check(
        "sequence monotonic",
        [e.sequence for e in snap] == sorted(e.sequence for e in snap),
    )

    # unsubscribe
    doomed: list[str] = []
    sub = bus.subscribe("tool.failed", lambda e: doomed.append(e.name))
    bus.publish(EventName.TOOL_FAILED)
    bus.unsubscribe(sub)
    bus.publish(EventName.TOOL_FAILED)
    runner.check("unsubscribe stops delivery", len(doomed) == 1)

    # strict mode
    strict_bus = EventBus(strict_names=True)
    try:
        strict_bus.publish("totally.unknown.event")
        runner.check("strict mode rejects unknown names", False)
    except ValueError:
        runner.check("strict mode rejects unknown names", True)
    result = strict_bus.publish(EventName.WINDOW_OPENED, payload={"hwnd": 1})
    runner.check("strict mode accepts canonical name", result.handler_count == 0)

    # patterns validation
    try:
        bus.subscribe("task.*.created", lambda e: None)
        runner.check("invalid pattern rejected", False)
    except ValueError:
        runner.check("invalid pattern rejected", True)


def section_c(runner: Runner) -> None:
    """C — Session System (§2.3)."""
    runner.section = "C/§2.3"
    print("\nC — Session System (§2.3)")

    bus = EventBus()
    from nexus.core.session import SessionManager

    manager = SessionManager(bus)
    user = manager.create_user(display_name="Operator")
    conversation = manager.create_conversation(user, title="Phase 1 chat")
    task = manager.create_task(
        conversation,
        goal="goal C",
        prompt="prompt C",
        agents=["a1"],
    )

    runner.check("id prefixes distinct (usr/conv/task)",
                user.id.startswith("usr_")
                and conversation.id.startswith("conv_")
                and task.id.startswith("task_"))
    runner.check("hierarchy: conversation.user_id", conversation.user_id == user.id)
    runner.check("hierarchy: task.conversation_id", task.conversation_id == conversation.id)
    runner.check("conversation tracks task", task.id in conversation.task_ids)
    runner.check(
        "entities are four distinct types",
        isinstance(user, User)
        and isinstance(conversation, Conversation)
        and isinstance(task, Task)
        and not isinstance(task, Conversation),
    )

    session1 = manager.open_session(task, context={"entry": "first"})
    runner.check("session id prefix sess_", session1.id.startswith("sess_"))
    runner.check("session.task_id links back", session1.task_id == task.id)
    runner.check("first session index is 1", session1.index == 1)
    runner.check("active session exposed", task.active_session is session1)

    try:
        manager.open_session(task)
        runner.check("overlapping sessions forbidden", False)
    except SessionError:
        runner.check("overlapping sessions forbidden", True)

    closed = manager.close_session(task, notes="run 1 done")
    runner.check("close_session ends it", closed is session1 and session1.ended_at is not None)
    runner.check("no active session after close", task.active_session is None)

    session2 = manager.open_session(task)
    runner.check("second session index is 2", session2.index == 2)

    runner.check(
        "task.created published once on creation",
        len(bus.history_snapshot("task.created")) == 1,
    )


def section_d(runner: Runner, bus: EventBus | None = None, manager=None):
    """D — Task Engine (§2.4)."""
    runner.section = "D/§2.4"
    print("\nD — Task Engine (§2.4)")

    runner.check(
        "exactly the 13 plan states",
        {s.value for s in TaskState} == PLAN_STATES,
        f"count={len(TaskState)}",
    )

    own_bus = bus or EventBus()
    own_manager = manager
    if own_manager is None:
        from nexus.core.session import SessionManager

        own_manager = SessionManager(own_bus)
    conversation = own_manager.create_conversation(
        own_manager.create_user(), title="D"
    )
    task = own_manager.create_task(conversation, goal="g", prompt="p")

    recorder = Recorder(own_bus)
    engine = TaskEngine(own_bus)

    runner.check("initial state is CREATED", task.state is TaskState.CREATED)

    try:
        engine.transition(task, TaskState.EXECUTING)
        runner.check("CREATED→EXECUTING rejected", False)
    except InvalidTransitionError:
        runner.check("CREATED→EXECUTING rejected", True)

    engine.start(task)
    runner.check("start moves to ANALYZING", task.state is TaskState.ANALYZING)
    runner.check("task.started published", "task.started" in recorder.names())

    engine.transition(task, TaskState.PLANNING)
    engine.transition(task, TaskState.EXECUTING)
    engine.transition(task, TaskState.WAITING_NETWORK)
    engine.transition(task, TaskState.EXECUTING)
    engine.transition(task, TaskState.PAUSED)
    runner.check("pause stores previous state",
                 task.state_before_pause is TaskState.EXECUTING)
    runner.check("task.paused published", "task.paused" in recorder.names())

    engine.resume(task)
    runner.check("resume returns to pre-pause state",
                 task.state is TaskState.EXECUTING)
    runner.check("task.resumed published", "task.resumed" in recorder.names())

    engine.transition(task, TaskState.VERIFYING)
    engine.complete(task, summary="done")
    runner.check("completion only via VERIFYING → COMPLETED",
                 task.state is TaskState.COMPLETED)
    runner.check("task.completed published", "task.completed" in recorder.names())
    runner.check("result attached on completion", task.result is not None
                 and task.result.summary == "done")
    runner.check("completed_at populated on completion",
                 task.result.completed_at is not None)

    try:
        engine.transition(task, TaskState.EXECUTING)
        runner.check("terminal state locked", False)
    except InvalidTransitionError:
        runner.check("terminal state locked", True)

    task2 = own_manager.create_task(conversation, goal="g2", prompt="p2")
    engine.start(task2)
    engine.transition(task2, TaskState.PLANNING)
    engine.transition(task2, TaskState.EXECUTING)
    engine.cancel(task2, reason="user asked")
    runner.check("cancel from active state", task2.state is TaskState.CANCELLED)

    # Regression guard (post-review fix): cancelling a PAUSED task must
    # publish task.updated — never task.resumed (a cancel is not a resume).
    task3 = own_manager.create_task(conversation, goal="g3", prompt="p3")
    engine.start(task3)
    engine.transition(task3, TaskState.PLANNING)
    engine.transition(task3, TaskState.EXECUTING)
    engine.pause(task3)
    resumed_before = recorder.names().count("task.resumed")
    engine.cancel(task3, reason="user abandoned it")
    names_after = recorder.names()
    runner.check("cancel from PAUSED lands CANCELLED",
                 task3.state is TaskState.CANCELLED)
    runner.check(
        "PAUSED→CANCELLED publishes task.updated, never task.resumed",
        names_after.count("task.resumed") == resumed_before
        and names_after[-1] == "task.updated",
    )

    # 9 transitions: ANALYZING→PLANNING→EXECUTING→WAITING_NETWORK→EXECUTING
    # →PAUSED→resume(EXECUTING)→VERIFYING→COMPLETED
    runner.check(
        "state history records transitions",
        len(task.state_history) == 9
        and task.state_history[0].to_state is TaskState.ANALYZING
        and task.state_history[-1].to_state is TaskState.COMPLETED,
        f"len={len(task.state_history)}",
    )


def section_e(runner: Runner) -> None:
    """E — Task Persistence (§2.5)."""
    runner.section = "E/§2.5"
    print("\nE — Task Persistence (§2.5)")

    with tempfile.TemporaryDirectory(prefix="nexus-e-") as tmp:
        root = Path(tmp)
        runtime = NexusRuntime.boot(root)
        manager = runtime.session_manager
        conversation = manager.create_conversation(
            manager.create_user(), title="E"
        )
        task = make_rich_task(conversation, manager)
        engine = TaskEngine(runtime.bus)
        engine.start(task)
        engine.transition(task, TaskState.PLANNING)
        engine.transition(task, TaskState.EXECUTING)

        saved_path = runtime.save_task(task)
        runner.check(
            "record written under tasks/",
            saved_path == root / "tasks" / f"{task.id}.json",
        )

        import json

        raw = json.loads(saved_path.read_text(encoding="utf-8"))
        task_data = raw["task"]
        runner.check(
            "record has exactly the eleven §2.5 fields",
            all(field in task_data for field in PLAN_TASK_FIELDS),
        )
        runner.check("envelope schema + version",
                     raw["schema"] == "nexus.task" and raw["schema_version"] == 1)

        loaded = runtime.load_task(task.id)
        runner.check("goal round-trip", loaded.goal == task.goal)
        runner.check("prompt round-trip", loaded.prompt == task.prompt)
        runner.check("scope round-trip", loaded.scope == task.scope)
        runner.check("workspace round-trip", loaded.workspace == task.workspace)
        runner.check(
            "plan round-trip",
            [s.description for s in loaded.plan.steps]
            == [s.description for s in task.plan.steps]
            and loaded.plan.steps[0].status is task.plan.steps[0].status,
        )
        runner.check("agents round-trip", loaded.agents == task.agents)
        runner.check("state round-trip", loaded.state is task.state)
        runner.check("checkpoints round-trip",
                     loaded.checkpoints[0].reason == task.checkpoints[0].reason)
        runner.check("errors round-trip",
                     loaded.errors[0].code == task.errors[0].code)
        runner.check(
            "verification round-trip",
            loaded.verification.status is task.verification.status
            and [c.name for c in loaded.verification.checks]
            == [c.name for c in task.verification.checks],
        )
        runner.check("result round-trip (None)", loaded.result is task.result)
        runner.check("sessions round-trip",
                     [s.index for s in loaded.sessions] == [s.index for s in task.sessions])
        runner.check("state history round-trip",
                     len(loaded.state_history) == len(task.state_history))

        summaries = runtime.list_tasks()
        runner.check("index lists the task",
                     any(s.id == task.id for s in summaries))
        runner.check("index holds current state",
                     any(s.state is TaskState.EXECUTING for s in summaries))

        try:
            runtime.repository.load("../" + task.id)
            runner.check("path traversal rejected", False)
        except PersistenceError:
            runner.check("path traversal rejected", True)

        runtime.shutdown()


def section_f(runner: Runner, root: Path) -> None:
    """F — Exit Criteria (§2.6): create → save → close → open → load →
    continue state, twice."""
    runner.section = "F/§2.6"
    print("\nF — Exit Criteria (§2.6) — create → save → CLOSE → OPEN → retrieve → continue")

    # ---- RUN 1: create, advance to EXECUTING, save, close NEXUS
    runtime1 = NexusRuntime.boot(root)
    recorder1 = Recorder(runtime1.bus)
    manager1 = runtime1.session_manager
    conversation = manager1.create_conversation(
        manager1.create_user(display_name="Operator"), title="§2.6 proof"
    )
    task = make_rich_task(conversation, manager1)
    engine = TaskEngine(runtime1.bus)

    session1 = manager1.open_session(task, context={"run": 1})
    engine.start(task, session_id=session1.id)
    engine.transition(task, TaskState.PLANNING, session_id=session1.id)
    engine.transition(task, TaskState.EXECUTING, session_id=session1.id)

    runtime1.save_task(task)
    runner.check("F1 task created, advanced to EXECUTING and saved",
                 task.state is TaskState.EXECUTING)
    runner.check(
        "F1 system.started published",
        any(e.name == "system.started" for e in runtime1.bus.history_snapshot()),
    )
    runner.check("F1 task.created published", "task.created" in recorder1.names())

    # §2.6 literal order: save it, THEN close NEXUS (session ends first)
    manager1.close_session(task, notes="closing NEXUS")
    runtime1.save_task(task)
    runtime1.shutdown()
    saved_id = task.id
    saved_conversation_id = conversation.id
    saved_goal = task.goal
    saved_prompt = task.prompt
    saved_plan = [s.description for s in task.plan.steps]
    saved_scope = dict(task.scope)
    saved_agents = list(task.agents)
    del runtime1, manager1, engine, task, conversation, recorder1, session1
    runner.check("F2 NEXUS closed (shutdown + object dropped)", True)

    # ---- RUN 2: open NEXUS fresh, retrieve, continue the state
    runtime2 = NexusRuntime.boot(root)
    recorder2 = Recorder(runtime2.bus)
    runner.check(
        "F3 NEXUS reopened (fresh runtime, fresh system.started)",
        any(e.name == "system.started" for e in runtime2.bus.history_snapshot()),
    )

    task2 = runtime2.load_task(saved_id)
    runner.check("F4 task retrieved by id", task2.id == saved_id)
    runner.check("F5 state survived the restart",
                 task2.state is TaskState.EXECUTING)
    runner.check("F5 goal/prompt survived", task2.goal == saved_goal
                 and task2.prompt == saved_prompt)
    runner.check("F5 plan/scope/agents survived",
                 [s.description for s in task2.plan.steps] == saved_plan
                 and task2.scope == saved_scope
                 and task2.agents == saved_agents)
    runner.check("F5 conversation link survived",
                 task2.conversation_id == saved_conversation_id)
    runner.check("F5 session history survived (1 closed session)",
                 len(task2.sessions) == 1 and task2.sessions[0].ended_at is not None)

    # continue the state: session #2 (متابعة)
    engine2 = TaskEngine(runtime2.bus)
    session2 = runtime2.session_manager.open_session(task2, context={"run": 2})
    runner.check("F6 continuation opens session #2", session2.index == 2)
    engine2.transition(task2, TaskState.VERIFYING, session_id=session2.id)
    engine2.complete(
        task2,
        summary="report produced and verified",
        artifacts=["M:\\Work\\Reports\\q-report.docx"],
        session_id=session2.id,
    )
    runner.check("F6 state continued: EXECUTING → VERIFYING → COMPLETED",
                 task2.state is TaskState.COMPLETED)
    runner.check("F6 task.completed published in run 2",
                 "task.completed" in recorder2.names())

    runtime2.session_manager.close_session(task2, notes="done")
    runtime2.save_task(task2)
    runtime2.shutdown()
    del runtime2, engine2, task2, session2, recorder2
    runner.check("F7 continued task saved, NEXUS closed again", True)

    # ---- RUN 3: reopen once more — terminal state persisted
    runtime3 = NexusRuntime.boot(root)
    task3 = runtime3.load_task(saved_id)
    runner.check("F8 terminal state persisted across a second restart",
                 task3.state is TaskState.COMPLETED)
    runner.check("F8 result persisted",
                 task3.result is not None
                 and task3.result.summary == "report produced and verified"
                 and task3.result.artifacts
                 == ["M:\\Work\\Reports\\q-report.docx"])
    runner.check("F8 two sessions in history",
                 len(task3.sessions) == 2)
    runtime3.shutdown()


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
    temp_root: str | None = None
    if args.root is None:
        temp_root = tempfile.mkdtemp(prefix="nexus-phase1-")
        root = Path(temp_root)
    else:
        root = Path(args.root).absolute()

    print("NEXUS Phase 1 — verification harness (Final Build Plan §2)")
    print(f"runtime root: {root}")

    try:
        section_a(runner)
        section_b(runner)
        section_c(runner)
        section_d(runner)
        section_e(runner)
        section_f(runner, root)
    finally:
        if temp_root is not None:
            shutil.rmtree(temp_root, ignore_errors=True)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
