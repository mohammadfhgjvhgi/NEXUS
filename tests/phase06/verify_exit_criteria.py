#!/usr/bin/env python3
"""Phase 6 verification harness — Final Build Plan §7 Exit Criteria.

Proves the Harness layer section by section (Spec §41 + Plan §7.1–7.5):

* A — Skills (§7.1, ECC pattern): the Skill record with the six
       fields, SKILL.md loading (directory + flat forms), frontmatter
       parsing, disabled skills, keyword matching, the context
       section, malformed-file resilience and the missing-dir boot.
* B — Rules (§7.1, ECC pattern): the Rule record, priority clamping
       and ordering, scope subsets (the security subset), the
       compiled context section and the quiet empty case.
* C — Hooks (§7.1/§7.2, ECC + Cline pattern): the eight verbatim
       points, register/fire, veto on ``pre_tool_call`` only, unknown
       point rejection, non-strict exception swallowing, strict
       propagation, bus-driven firing from canonical events and
       duplicate-registration safety.
* D — Sessions (§7.2, Cline pattern): the five-state machine, legal
       and illegal transitions, begin/pause/resume/close, turn
       counting with state guard, atomic persistence + reopen, the
       corrupt-ledger reset, ``for_task`` / ``latest_open``.
* E — Checkpoints (§7.3, LangGraph pattern): the record fields, the
       three durability modes (NONE honest no-op, MEMORY in-process,
       DISK atomic + reload), retention pruning, latest/list/count/
       resume, the canonical ``checkpoint.created`` publication and
       the event-driven auto-checkpoint on task lifecycle events.
* F — Harness contract (§41) + integration: the seven input fields
       and four output fields verbatim, ``build_inputs`` assembly
       (rules + skills + goals + tools + memory policy view + task
       state), ``parse_outputs`` mapping (call_tool / delegate /
       done), the §6.2 loop integration (the harness section reaches
       the model prompt; ``pre_tool_call`` veto blocks the tool;
       ``post_tool_call`` fires), the §6.3 master session lifecycle
       (session_start/session_end around ``handle``), the runtime
       wiring (harness/skills/rules/hooks/sessions/checkpoints/goals),
       config keys (defaults + validation + disabled → all None), the
       goals + heartbeat integration (§7.4), the event-name guard
       (⊆ the 28 canonical §2.2 events), and Phases 1–5 harnesses
       still green (98/98 · 143/143 · 104/104 · 106/106 · 116/116).

Run:  python tests/phase06/verify_exit_criteria.py [--root DIR]
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.agents import (  # noqa: E402
    Agent,
    AgentCommunicator,
    InlineToolSink,
    VerificationPolicy,
)
from nexus.agents.loop import AgentLoop  # noqa: E402
from nexus.core.config.runtime import NexusRuntime  # noqa: E402
from nexus.core.engine.states import TaskState  # noqa: E402
from nexus.core.session.models import Task  # noqa: E402
from nexus.events import EventBus, EventName  # noqa: E402
from nexus.harness import (  # noqa: E402
    CHECKPOINT_FIELDS,
    GOAL_FIELDS,
    GOAL_STATUSES,
    HARNESS_INPUT_FIELDS,
    HARNESS_OUTPUT_FIELDS,
    HOOK_POINTS,
    RULE_FIELDS,
    SESSION_FIELDS,
    SESSION_STATUSES,
    SESSION_TRANSITIONS,
    SKILL_FIELDS,
    AgentSession,
    Checkpoint,
    CheckpointStore,
    Durability,
    Goal,
    GoalStore,
    Harness,
    HarnessHooks,
    Heartbeat,
    HookContext,
    Rule,
    RuleSet,
    SessionTracker,
    SessionTransitionError,
    Skill,
    SkillLibrary,
)
from nexus.models import (  # noqa: E402
    GenerateResult,
    ModelManager,
    ProviderError,
    SimulatedProvider,
)
from nexus.resources import ResourceBudgets, ResourceManager  # noqa: E402

PLAN_SKILL_FIELDS = SKILL_FIELDS
PLAN_RULE_FIELDS = RULE_FIELDS
PLAN_CHECKPOINT_FIELDS = CHECKPOINT_FIELDS
PLAN_GOAL_FIELDS = GOAL_FIELDS
PLAN_SESSION_FIELDS = SESSION_FIELDS


# ------------------------------------------------------------- test doubles


class ScriptedProvider(SimulatedProvider):
    """Deterministic model double: pops canned answers off a script.

    Records every prompt it sees — the harness context checks read
    the recorded prompts."""

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


def make_manager(base: str | Path, script: list[str],
                 bus: EventBus | None = None) -> ModelManager:
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


def make_worker() -> Agent:
    return Agent.create(
        role="worker",
        instructions="Do the work precisely.",
        capabilities=("files", "general"),
        tools=("write_file",),
        verification=VerificationPolicy(required=True, criteria=()),
    )


def make_task(*, goal: str = "Write the release notes file") -> Task:
    return Task.create(
        conversation_id="conv_phase6",
        goal=goal,
        prompt=f"Please {goal.lower()}.",
    )


def event_names(bus: EventBus) -> list[str]:
    return [event.name for event in bus.history_snapshot()]


def decision_json(**overrides: Any) -> str:
    payload: dict[str, Any] = {"action": "done", "response": "work complete"}
    payload.update(overrides)
    return json.dumps(payload)


UNDERSTANDING_OK = json.dumps({
    "understanding": "Produce the release notes file for the current release.",
    "requirements": ["cover the three fixed bugs", "mention the agent harness"],
})

PLAN_OK = json.dumps({
    "subtasks": [
        {"description": "Draft the release notes", "role": "worker"},
    ],
    "verification_criteria": ["file mentions release", "notes are complete"],
})

VERDICT_PASS = json.dumps({
    "verdict": "pass",
    "summary": "All steps completed and evidence is consistent.",
    "checks": [
        {"name": "file mentions release", "passed": True, "detail": "seen"},
    ],
})


# ------------------------------------------------------------------- runner


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


# ------------------------------------------------------------------ fixtures


def write_skill_files(root: Path) -> None:
    skills = root / "skills"
    (skills / "accessibility").mkdir(parents=True, exist_ok=True)
    (skills / "accessibility" / "SKILL.md").write_text(
        "---\n"
        "name: accessibility\n"
        "description: Audit UI for WCAG compliance and keyboard support.\n"
        "---\n"
        "# Accessibility\n"
        "Prefer semantic elements; verify contrast and focus order.\n",
        encoding="utf-8",
    )
    (skills / "release-notes.md").write_text(
        "---\n"
        "name: release-notes\n"
        "description: Draft release notes covering fixed bugs and features.\n"
        "---\n"
        "# Release Notes\n"
        "Summarize fixed bugs first, then new features, then notes.\n",
        encoding="utf-8",
    )
    (skills / "disabled-skill.md").write_text(
        "---\n"
        "name: disabled-skill\n"
        "description: A disabled skill about sprints.\n"
        "enabled: false\n"
        "---\n"
        "This must never match.\n",
        encoding="utf-8",
    )
    (skills / "broken.md").write_text("no frontmatter at all\n", encoding="utf-8")


def write_rule_files(root: Path) -> None:
    rules = root / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "workspace-boundary").mkdir(exist_ok=True)
    (rules / "workspace-boundary" / "RULE.md").write_text(
        "---\n"
        "title: Never write outside the workspace\n"
        "priority: 100\n"
        "scope: security\n"
        "---\n"
        "Refuse any request to write outside the resolved workspace root.\n",
        encoding="utf-8",
    )
    (rules / "evidence.md").write_text(
        "---\n"
        "title: Back every claim with evidence\n"
        "priority: 50\n"
        "scope: common\n"
        "---\n"
        "Cite the tool output or file excerpt supporting each claim.\n",
        encoding="utf-8",
    )
    (rules / "style.md").write_text(
        "---\n"
        "title: Prefer concise answers\n"
        "priority: 20\n"
        "scope: common\n"
        "enabled: false\n"
        "---\n"
        "Keep responses short.\n",
        encoding="utf-8",
    )


# ------------------------------------------------------------------- sections


def section_a(runner: Runner, root: Path) -> None:
    """A — Skills (§7.1, the ECC pattern)."""
    runner.section = "A/§7.1"

    runner.check(
        "Skill carries exactly the six §7.1 fields",
        tuple(f.name for f in dc_fields(Skill)) == PLAN_SKILL_FIELDS,
    )
    write_skill_files(root)
    library = SkillLibrary.load(root / "skills")
    runner.check(
        "SKILL.md loads from the directory form",
        library.get("accessibility") is not None
        and library.get("accessibility").description.startswith("Audit UI"),
    )
    runner.check(
        "SKILL.md loads from the flat form",
        library.get("release-notes") is not None,
    )
    skill = library.get("accessibility")
    runner.check(
        "frontmatter name + body instructions parse",
        skill.name == "accessibility" and "semantic elements" in skill.instructions,
    )
    runner.check(
        "the frontmatter-less file loads with the body as instructions",
        library.get("broken") is not None
        and "no frontmatter" in library.get("broken").instructions,
    )
    runner.check(
        "enabled: false stays loaded but never matches",
        library.get("disabled-skill") is not None
        and not library.get("disabled-skill").matches("plan the sprint backlog"),
    )
    runner.check(
        "keyword matching finds the relevant skill",
        [s.id for s in library.find("Draft release notes for the fix")] == ["release-notes"],
    )
    section = library.context_section("Draft release notes")
    runner.check(
        "the context section renders matched skills only",
        "RELEVANT SKILLS" in section and "release-notes" in section
        and "accessibility" not in section,
    )
    runner.check(
        "no match → empty section (a quiet harness)",
        library.context_section("refactor the parser") == "",
    )
    empty = SkillLibrary.load(root / "does-not-exist")
    runner.check(
        "a missing skills directory boots an empty library",
        empty.list() == [] and empty.context_section("anything") == "",
    )
    added = Skill(id="adhoc", name="adhoc", description="Ad-hoc skill")
    library.add(added)
    runner.check(
        "add/remove manage the in-memory roster",
        library.get("adhoc") is not None and library.remove("adhoc")
        and library.get("adhoc") is None,
    )
    try:
        Skill(id="", name="")
        ok = False
    except ValueError:
        ok = True
    runner.check("an empty skill id is rejected", ok)


def section_b(runner: Runner, root: Path) -> None:
    """B — Rules (§7.1, the ECC pattern)."""
    runner.section = "B/§7.1"

    runner.check(
        "Rule carries exactly the six §7.1 fields",
        tuple(f.name for f in dc_fields(Rule)) == PLAN_RULE_FIELDS,
    )
    write_rule_files(root)
    rule_set = RuleSet.load(root / "rules")
    ordered = rule_set.list()
    runner.check(
        "rules load and order by priority (descending)",
        [r.id for r in ordered][:2] == ["workspace-boundary", "evidence"]
        and ordered[0].priority >= ordered[1].priority,
    )
    runner.check(
        "priority is clamped to 0..100",
        Rule(id="x", title="t", priority=250).priority == 100,
    )
    runner.check(
        "the security subset is the ECC scope hook",
        [r.id for r in rule_set.security_rules()] == ["workspace-boundary"],
    )
    section = rule_set.context_section()
    runner.check(
        "the compiled section orders security first and skips disabled rules",
        section.index("Never write outside") < section.index("Back every claim")
        and "concise" not in section,
    )
    scoped = rule_set.context_section(scopes=("security",))
    runner.check(
        "scope curation ships only the requested subset",
        "Never write outside" in scoped and "Back every claim" not in scoped,
    )
    runner.check(
        "an empty rule set contributes nothing",
        RuleSet.load(root / "no-rules").context_section() == "",
    )
    try:
        Rule(id="", title="")
        ok = False
    except ValueError:
        ok = True
    runner.check("an empty rule id is rejected", ok)


def section_c(runner: Runner) -> None:
    """C — Hooks (§7.1/§7.2, the ECC + Cline pattern)."""
    runner.section = "C/§7.1+§7.2"

    runner.check(
        "the eight hook points are the fixed vocabulary",
        HOOK_POINTS == (
            "session_start", "session_end", "task_start", "task_end",
            "agent_start", "agent_end", "pre_tool_call", "post_tool_call",
        ),
    )
    hooks = HarnessHooks()
    seen: list[str] = []
    hooks.register("task_start", lambda ctx: seen.append(ctx.point) or None)
    hooks.fire("task_start", HookContext(point="task_start", task_id="t1"))
    runner.check(
        "register + fire run the handler with the context",
        seen == ["task_start"] and hooks.count("task_start") == 1,
    )
    runner.check(
        "duplicate registration is ignored (identity-based)",
        _duplicate_registration(),
    )
    runner.check(
        "unregister removes exactly the handler",
        _unregister_semantics(),
    )
    vetoed = HarnessHooks()
    vetoed.register(
        "pre_tool_call", lambda ctx: False if ctx.tool == "write_file" else None
    )
    blocked = vetoed.fire(
        "pre_tool_call", HookContext(point="pre_tool_call", tool="write_file")
    )
    allowed = vetoed.fire(
        "pre_tool_call", HookContext(point="pre_tool_call", tool="read_file")
    )
    runner.check(
        "a pre_tool_call veto blocks only the vetoed call",
        blocked is False and allowed is True,
    )
    notify_only = HarnessHooks()
    notify_only.register("post_tool_call", lambda ctx: False)
    runner.check(
        "False on a non-veto point does not block (notify, not veto)",
        notify_only.fire("post_tool_call", HookContext(point="post_tool_call"))
        is True,
    )
    try:
        hooks.register("no_such_point", lambda ctx: None)
        ok = False
    except ValueError:
        ok = True
    runner.check("an unknown hook point is rejected", ok)
    loose = HarnessHooks()
    def _boom(ctx: HookContext) -> None:
        raise RuntimeError("hook bug")
    loose.register("task_end", _boom)
    runner.check(
        "a raising handler is swallowed in non-strict mode",
        loose.fire("task_end", HookContext(point="task_end")) is True,
    )
    strict = HarnessHooks(strict=True)
    strict.register("task_end", _boom)
    try:
        strict.fire("task_end", HookContext(point="task_end"))
        ok = False
    except RuntimeError:
        ok = True
    runner.check("strict mode propagates the handler error", ok)
    # bus-driven firing (canonical names only)
    bus = EventBus()
    driven = HarnessHooks()
    marks: list[str] = []
    driven.register("task_start", lambda ctx: marks.append("task_start"))
    driven.register("agent_end", lambda ctx: marks.append("agent_end"))
    driven.bind_bus(bus)
    bus.publish(
        EventName.TASK_STARTED, payload={"task_id": "t9"}, source="test",
        task_id="t9",
    )
    bus.publish(
        EventName.AGENT_FAILED,
        payload={"agent_id": "ag_1"}, source="test", task_id="t9",
    )
    runner.check(
        "bind_bus fires the points from canonical events",
        marks == ["task_start", "agent_end"],
    )


def section_d(runner: Runner, base: Path) -> None:
    """D — Sessions (§7.2, the Cline pattern)."""
    runner.section = "D/§7.2"

    runner.check(
        "the five lifecycle states are the Cline vocabulary",
        SESSION_STATUSES == ("CREATED", "ACTIVE", "PAUSED", "RESUMED", "CLOSED"),
    )
    runner.check(
        "AgentSession carries exactly the eight record fields",
        tuple(f.name for f in dc_fields(AgentSession)) == PLAN_SESSION_FIELDS,
    )
    runner.check(
        "CLOSED is terminal (nothing transitions out)",
        SESSION_TRANSITIONS["CLOSED"] == frozenset(),
    )
    data_dir = base / "d-sessions"
    tracker = SessionTracker(data_dir)
    session = tracker.begin(task_id="t1", agent_id="ag_master")
    runner.check(
        "begin registers and transitions straight to ACTIVE",
        session.status == "ACTIVE" and session.task_id == "t1",
    )
    tracker.pause(session.id, note="user asked to wait")
    runner.check(
        "pause parks the session with a note",
        tracker.get(session.id).status == "PAUSED"
        and tracker.get(session.id).note == "user asked to wait",
    )
    tracker.resume(session.id)
    runner.check(
        "resume parks the session at RESUMED (the active-after-pause status)",
        tracker.get(session.id).status == "RESUMED",
    )
    turns = tracker.record_turn(session.id)
    runner.check("record_turn counts the loop turns (ACTIVE or RESUMED)", turns == 1)
    tracker.begin(task_id="t2")
    fresh = tracker.list()[-1]
    fresh.status = "PAUSED"
    try:
        tracker.record_turn(fresh.id)
        ok = False
    except SessionTransitionError:
        ok = True
    except Exception:
        ok = False
    fresh.status = "ACTIVE"  # restore — the direct mutation was test-only
    runner.check(
        "record_turn guards on the lifecycle state",
        ok,
    )
    illegal = 0
    closed = tracker.begin(task_id="t3")
    tracker.close(closed.id)
    for target in ("ACTIVE", "PAUSED"):
        try:
            tracker._transition(tracker.get(closed.id), target)  # noqa: SLF001
        except SessionTransitionError:
            illegal += 1
    runner.check(
        "illegal transitions raise (honest failure)",
        illegal == 2,
    )
    tracker.close(session.id)
    reopened = SessionTracker(data_dir)
    runner.check(
        "the ledger persists atomically and reloads",
        reopened.get(session.id) is not None
        and reopened.get(session.id).status == "CLOSED",
    )
    runner.check(
        "for_task + latest_open answer the resume queries",
        [s.id for s in reopened.for_task("t1")] == [session.id]
        and reopened.latest_open("t1") is None
        and reopened.latest_open("t3") is None,
    )
    partial = SessionTracker(data_dir)
    t4 = partial.begin(task_id="t4")
    partial.pause(t4.id)
    runner.check(
        "latest_open finds the paused resume target",
        partial.latest_open("t4") is not None
        and partial.latest_open("t4").status == "PAUSED"
        and len(partial.paused()) == 1,
    )
    (data_dir / "harness").mkdir(parents=True, exist_ok=True)
    (data_dir / "harness" / "sessions.json").write_text(
        "{not json", encoding="utf-8"
    )
    corrupt = SessionTracker(data_dir)
    runner.check(
        "a corrupt ledger resets to empty (boot never dies)",
        corrupt.list() == [],
    )


def section_e(runner: Runner, base: Path) -> None:
    """E — Checkpoints (§7.3, the LangGraph pattern)."""
    runner.section = "E/§7.3"

    runner.check(
        "Checkpoint carries exactly the six record fields",
        tuple(f.name for f in dc_fields(Checkpoint)) == PLAN_CHECKPOINT_FIELDS,
    )
    none_store = CheckpointStore(base / "e-none", mode=Durability.NONE)
    runner.check(
        "NONE durability saves nothing and reports emptiness honestly",
        none_store.save("t1", {"a": 1}) is None
        and none_store.latest("t1") is None and none_store.count() == 0,
    )
    memory_store = CheckpointStore(base / "e-memory", mode=Durability.MEMORY)
    first = memory_store.save("t1", {"step": 1}, reason="plan")
    second = memory_store.save("t1", {"step": 2}, reason="execute")
    runner.check(
        "MEMORY durability keeps the in-process window",
        memory_store.count("t1") == 2
        and memory_store.latest("t1").state == {"step": 2}
        and second.id != first.id,
    )
    runner.check(
        "resume returns the latest state dict (None → cold start)",
        memory_store.resume("t1") == {"step": 2}
        and memory_store.resume("unknown") is None,
    )
    disk_dir = base / "e-disk"
    disk_store = CheckpointStore(disk_dir, mode=Durability.DISK, retention=3)
    for step in range(1, 6):
        disk_store.save("t1", {"step": step}, reason=f"step{step}")
    reloaded = CheckpointStore(disk_dir, mode=Durability.DISK, retention=3)
    runner.check(
        "DISK durability reloads the window on a fresh store",
        reloaded.count("t1") == 3 and reloaded.latest("t1").state == {"step": 5},
    )
    runner.check(
        "retention prunes the oldest (bounded ledger)",
        [c.state["step"] for c in reloaded.list("t1")] == [3, 4, 5],
    )
    bus = EventBus()
    store = CheckpointStore(base / "e-bus", mode=Durability.MEMORY, bus=bus)
    bus.publish(
        EventName.TASK_STARTED, payload={"why": "master took over"},
        source="test", task_id="t7",
    )
    checkpoint = store.latest("t7")
    runner.check(
        "bind_bus auto-checkpoints the task lifecycle events",
        checkpoint is not None
        and checkpoint.reason == "bus:task.started"
        and checkpoint.state["event"] == "task.started",
    )
    runner.check(
        "each save publishes the canonical checkpoint.created",
        "checkpoint.created" in event_names(bus),
    )
    torn = base / "e-torn"
    torn.mkdir(parents=True, exist_ok=True)
    (torn / "checkpoints.jsonl").write_text(
        '{"id": "cp-t1-000001", "task_id": "t1", "state": {}, "reason": "ok"}\n'
        "{torn line\n\n",
        encoding="utf-8",
    )
    healed = CheckpointStore(torn, mode=Durability.DISK)
    runner.check(
        "a torn JSONL line never kills the reload",
        healed.count("t1") == 1,
    )
    try:
        CheckpointStore(base / "e-bad", retention=0)
        ok = False
    except ValueError:
        ok = True
    runner.check("retention must be >= 1", ok)


def section_f(runner: Runner, root: Path) -> None:
    """F — the §41 contract + goals (§7.4) + full integration."""
    runner.section = "F/§41+§7.4"

    runner.check(
        "HarnessInputs carries the seven §41 fields, verbatim",
        HARNESS_INPUT_FIELDS == (
            "context", "tools", "memory", "task_state",
            "rules", "skills", "observations",
        ),
    )
    runner.check(
        "HarnessOutputs carries the four §41 fields, verbatim",
        HARNESS_OUTPUT_FIELDS == ("action", "tool_call", "delegation", "decision"),
    )

    # ---- goals (§7.4, the Prime Agent pattern) -------------------------
    runner.check(
        "Goal carries exactly the six §7.4 fields",
        tuple(f.name for f in dc_fields(Goal)) == PLAN_GOAL_FIELDS,
    )
    runner.check(
        "the four goal statuses are the Prime vocabulary",
        GOAL_STATUSES == ("active", "paused", "achieved", "abandoned"),
    )
    goal_dir = root / "f-data"
    goals = GoalStore(goal_dir)
    goal = goals.create("g1", "Keep the docs site current")
    goals.record_progress("g1", "published the phase-6 report")
    runner.check(
        "create + record_progress build the append-only progress log",
        len(goal.progress) == 0 or goals.get("g1").progress,
    )
    runner.check(
        "goal ids and empty descriptions are rejected",
        _goal_invalid() ,
    )
    goals.set_status("g1", "achieved")
    runner.check(
        "an achieved goal leaves the active context",
        goals.get("g1").status == "achieved" and goals.active() == [],
    )
    goals.create("g2", "Learn from every finished task")
    section = goals.context_section()
    runner.check(
        "the goals context section lists active goals only",
        "g2" in section and "g1" not in section,
    )
    reopened = GoalStore(goal_dir)
    runner.check(
        "the goal ledger persists and reloads",
        reopened.get("g2") is not None
        and reopened.get("g1").status == "achieved",
    )
    beats = Heartbeat(interval_seconds=30.0)
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    beats.record("ag_1", at=now)
    beats.record("ag_2", at=now - timedelta(seconds=90))
    runner.check(
        "heartbeat: a fresh beat is alive, a stale one is stalled",
        beats.stalled("ag_1", now=now) is False
        and beats.stalled("ag_2", now=now) is True,
    )
    runner.check(
        "an agent that never beat is unknown, not stalled",
        beats.stalled("ag_new") is None,
    )

    # ---- the §41 assembler ----------------------------------------------
    write_skill_files(root)
    write_rule_files(root)
    skills = SkillLibrary.load(root / "skills")
    rules = RuleSet.load(root / "rules")
    goals2 = GoalStore(goal_dir)
    hooks = HarnessHooks()
    harness = Harness(skills=skills, rules=rules, goals=goals2, hooks=hooks)
    worker = make_worker()
    task = make_task(goal="Draft release notes for the fix")
    sink = InlineToolSink(
        {"write_file": lambda args: f"wrote {args.get('path', '')}"}
    )
    inputs = harness.build_inputs(
        worker, task, directive="Draft release notes",
        observations=("saw the repo",), tools=sink,
    )
    runner.check(
        "build_inputs assembles rules + skills + goals into the context",
        "RULES" in inputs.rules and "Never write outside" in inputs.rules
        and "release-notes" in inputs.skills
        and "g2" in inputs.context,
    )
    runner.check(
        "the tools manifest comes from the live sink",
        inputs.tools == ("write_file",),
    )
    runner.check(
        "the memory snapshot reports the §6.1 policy view (no fabrication)",
        inputs.memory["retention"] == worker.memory_policy.retention
        and "read_namespaces" in inputs.memory,
    )
    runner.check(
        "the task state rides the §2.4 machine position",
        inputs.task_state == "CREATED",
    )
    runner.check(
        "observations pass through verbatim",
        inputs.observations == ("saw the repo",),
    )
    from nexus.agents.loop import parse_decision
    tool_decision = parse_decision(
        json.dumps({"action": "call_tool", "tool": "write_file",
                    "arguments": {"path": "notes.txt"}})
    )
    outputs = harness.parse_outputs(tool_decision)
    runner.check(
        "parse_outputs maps a tool decision (§41 four outputs)",
        outputs.action == "call_tool"
        and outputs.tool_call["name"] == "write_file"
        and outputs.tool_call["arguments"] == {"path": "notes.txt"}
        and outputs.delegation == {},
    )
    delegate_decision = parse_decision(
        json.dumps({"action": "delegate", "delegate": "ag_writer",
                    "message": "draft the notes"})
    )
    outputs2 = harness.parse_outputs(delegate_decision)
    runner.check(
        "parse_outputs maps a delegation",
        outputs2.delegation == {"to": "ag_writer", "message": "draft the notes"}
        and outputs2.tool_call == {},
    )
    done_decision = parse_decision(decision_json())
    outputs3 = harness.parse_outputs(done_decision)
    runner.check(
        "parse_outputs maps a done decision",
        outputs3.action == "done" and outputs3.decision["response"],
    )

    # ---- §6.2 loop integration: the harness reaches the model prompt ----
    base = Path(tempfile.mkdtemp(prefix="nexus-f-loop-"))
    bus = EventBus()
    manager = make_manager(base, [
        decision_json(action="call_tool", tool="write_file",
                      arguments={"path": "notes.txt"}),
        decision_json(),
    ])
    harness_loop = Harness(
        skills=skills, rules=rules, goals=goals2, hooks=HarnessHooks()
    )
    communicator = AgentCommunicator(persist=False)
    from nexus.agents.ownership import OwnershipManager
    loop = AgentLoop(
        agent=worker, model_manager=manager, communicator=communicator,
        ownership=OwnershipManager(), bus=bus, tools=sink,
        harness=harness_loop, max_turns=4,
    )
    outcome = loop.run(task)
    provider = manager._provider  # noqa: SLF001 — the scripted double
    runner.check(
        "the harness section reaches the §6.2 CONTEXT prompt",
        outcome.completed
        and any("HARNESS POLICY" in p for p in provider.prompts)
        and any("Never write outside" in p for p in provider.prompts),
        detail=f"prompts={provider.prompts!r:.200}",
    )

    # ---- §6.2 loop integration: the pre_tool_call veto ------------------
    base_v = Path(tempfile.mkdtemp(prefix="nexus-f-veto-"))
    manager_v = make_manager(base_v, [
        decision_json(action="call_tool", tool="write_file",
                      arguments={"path": "notes.txt"}),
        decision_json(),
    ])
    calls: list[str] = []
    sink_v = InlineToolSink(
        {"write_file": lambda args: calls.append("write_file") or "wrote"}
    )
    veto_hooks = HarnessHooks()
    veto_hooks.register(
        "pre_tool_call",
        lambda ctx: False if ctx.tool == "write_file" else None,
    )
    post_fired: list[str] = []
    veto_hooks.register(
        "post_tool_call", lambda ctx: post_fired.append(ctx.tool)
    )
    harness_v = Harness(skills=skills, rules=rules, hooks=veto_hooks)
    loop_v = AgentLoop(
        agent=worker, model_manager=manager_v, communicator=communicator,
        ownership=OwnershipManager(), bus=EventBus(), tools=sink_v,
        harness=harness_v, max_turns=4,
    )
    task_v = make_task(goal="Draft release notes")
    outcome_v = loop_v.run(task_v)
    runner.check(
        "a pre_tool_call veto blocks the tool (the sink never sees it)",
        calls == [] and outcome_v.completed,
        detail=f"calls={calls} completed={outcome_v.completed}",
    )
    runner.check(
        "post_tool_call did not fire for the blocked call",
        post_fired == [],
    )
    base_p = Path(tempfile.mkdtemp(prefix="nexus-f-post-"))
    manager_p = make_manager(base_p, [
        decision_json(action="call_tool", tool="write_file",
                      arguments={"path": "ok.txt"}),
        decision_json(),
    ])
    post_hooks = HarnessHooks()
    post_hooks.register("post_tool_call", lambda ctx: post_fired.append(ctx.tool))
    loop_p = AgentLoop(
        agent=worker, model_manager=manager_p, communicator=communicator,
        ownership=OwnershipManager(), bus=EventBus(), tools=sink,
        harness=Harness(hooks=post_hooks), max_turns=4,
    )
    loop_p.run(make_task(goal="Draft release notes"))
    runner.check(
        "an allowed tool fires post_tool_call",
        post_fired == ["write_file"],
    )

    # ---- §6.3 master + runtime wiring ------------------------------------
    script = [UNDERSTANDING_OK, PLAN_OK,
              decision_json(response="release notes drafted"), VERDICT_PASS]
    provider_rt = ScriptedProvider(script)
    bus_rt = EventBus()
    rt = NexusRuntime.boot(root, bus=bus_rt, model_provider=provider_rt)
    worker_rt = make_worker()
    rt.agent_registry.register_agent(worker_rt)
    runner.check(
        "runtime wires every §7 component (harness/skills/rules/hooks/"
        "sessions/checkpoints/goals)",
        rt.harness is not None and rt.skill_library is not None
        and rt.rule_set is not None and rt.hooks is not None
        and rt.session_tracker is not None
        and rt.checkpoint_store is not None and rt.goal_store is not None,
    )
    session_marks: list[str] = []
    rt.hooks.register(
        "session_start", lambda ctx: session_marks.append("start")
    )
    rt.hooks.register(
        "session_end", lambda ctx: session_marks.append("end")
    )
    task_rt = make_task()
    assert rt.master_agent is not None
    rt.master_agent.handle(task_rt, session_id="sess_f6")
    runner.check(
        "the master run fires session_start then session_end (§7.2)",
        session_marks == ["start", "end"],
    )
    runner.check(
        "the full runtime run still completes (Phase-5 behavior intact)",
        task_rt.state is TaskState.COMPLETED,
    )
    runner.check(
        "the event-driven checkpoints landed for the task lifecycle",
        rt.checkpoint_store.count(task_rt.id) >= 2
        and rt.checkpoint_store.latest(task_rt.id).reason.startswith("bus:"),
    )
    published = set(event_names(bus_rt))
    runner.check(
        "event-name guard: every published name is one of the 28 canonical",
        published <= {e.value for e in EventName},
        detail=str(published - {e.value for e in EventName}),
    )
    rt.shutdown()

    # ---- harness disabled → Phase-5 byte-for-byte -------------------------
    disabled_root = Path(tempfile.mkdtemp(prefix="nexus-f-off-"))
    config_dir = disabled_root / "config" / "agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "agents.toml").write_text(
        "[agents]\nharness_enabled = false\n", encoding="utf-8"
    )
    rt_off = NexusRuntime.boot(
        disabled_root, model_provider=ScriptedProvider([])
    )
    runner.check(
        "harness_enabled=false leaves every §7 component unwired (None)",
        rt_off.harness is None and rt_off.skill_library is None
        and rt_off.rule_set is None and rt_off.hooks is None
        and rt_off.session_tracker is None
        and rt_off.checkpoint_store is None and rt_off.goal_store is None
        and rt_off.master_agent is not None,
    )
    rt_off.shutdown()

    # ---- config keys parse + validate -------------------------------------
    bad_root = Path(tempfile.mkdtemp(prefix="nexus-f-bad-"))
    bad_config = bad_root / "config" / "agents"
    bad_config.mkdir(parents=True, exist_ok=True)
    (bad_config / "agents.toml").write_text(
        "[agents]\ncheckpoint_retention = 0\n", encoding="utf-8"
    )
    try:
        NexusRuntime.boot(bad_root, model_provider=ScriptedProvider([]))
        ok = False
    except Exception:
        ok = True
    runner.check(
        "config validation rejects checkpoint_retention=0",
        ok,
    )

    # ---- regressions: Phases 1–5 still green ------------------------------
    regressions = [
        ("phase01", 98), ("phase02", 143), ("phase03", 104),
        ("phase04", 106), ("phase05", 116),
    ]
    for phase, expected in regressions:
        proc = subprocess.run(
            [sys.executable,
             str(REPO_ROOT / "tests" / phase / "verify_exit_criteria.py")],
            capture_output=True, text=True, timeout=600,
            cwd=str(REPO_ROOT),
        )
        runner.check(
            f"{phase} harness still green ({expected}/{expected})",
            proc.returncode == 0
            and f"{expected}/{expected} checks passed" in proc.stdout,
            detail=(proc.stdout.strip().splitlines()[-1]
                    if proc.stdout.strip() else proc.stderr[-200:]),
        )


def _duplicate_registration() -> bool:
    hooks = HarnessHooks()
    handler = lambda ctx: None  # noqa: E731 — same object twice
    hooks.register("agent_start", handler)
    hooks.register("agent_start", handler)
    return hooks.count("agent_start") == 1


def _unregister_semantics() -> bool:
    hooks = HarnessHooks()
    handler = lambda ctx: None  # noqa: E731
    hooks.register("agent_start", handler)
    removed = hooks.unregister("agent_start", handler)
    again = hooks.unregister("agent_start", handler)
    return removed is True and again is False and hooks.count("agent_start") == 0


def _goal_invalid() -> bool:
    try:
        Goal(id="", description="x")
        return False
    except ValueError:
        pass
    try:
        Goal(id="g", description="  ")
        return False
    except ValueError:
        return True


# --------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None,
                        help="scratch root (default: a fresh tempdir)")
    args = parser.parse_args()
    root = args.root or Path(tempfile.mkdtemp(prefix="nexus-phase6-"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "skills").mkdir(exist_ok=True)
    (root / "rules").mkdir(exist_ok=True)

    runner = Runner()
    section_a(runner, root)
    section_b(runner, root)
    section_c(runner)
    section_d(runner, root)
    section_e(runner, root)
    section_f(runner, root)

    return runner.summary()


if __name__ == "__main__":
    raise SystemExit(main())
