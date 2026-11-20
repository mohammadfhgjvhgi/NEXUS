"""Long-Horizon contracts (PHASE 25 — Long-Horizon Execution §25.1–§25.7).

The user's plan, verbatim::

    الهدف: «خذ المهمة واشتغل لحد ما تخلص.»
    (Take the task and work until it's done.)

    25.1  Goal persistence
    25.2  Background workers
    25.3  Long-running state
    25.4  Heartbeat
    25.5  Checkpoints
    25.6  Resume
    25.7  Deadline — 30 minutes · 2 hours · 8 hours · Until completion

The vocabulary below is the plan's nouns; the engines
(:mod:`nexus.horizon.goals` · ``.runner`` · ``.resume``) are the verbs.
Integration law — nothing here is copied, everything is composed:

* **§25.4 rides §23** — the runner beats the existing
  :class:`~nexus.health.HeartbeatMonitor` (``agent`` per step, ``task``
  at the milestones) and silence is derived from the clock, never from
  an exception;
* **§25.5 rides §22** — periodic checkpoints are captured through the
  existing :class:`~nexus.recovery.CheckpointManager` and the recorded
  id is persisted with the goal;
* **§25.6 rides §22.4** — resume refuses blind resumption: the
  persisted state is re-read from disk, verified, and a drifted or
  missing checkpoint refuses the resume outright
  (:class:`BlindResumeError`);
* **§25.7 is honest** — a bounded deadline stops the run with
  ``deadline_hit`` (never a fake completion); the four verbatim
  deadlines are the only vocabulary, and ``until_completion`` carries
  no deadline at all.

A deadline bounds ONE RUN, not the goal's life: resuming a
deadline-hit goal opens a fresh window of the same kind (documented
decision — the goal owner said «اشتغل لحد ما تخلص»).

Stdlib only.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Horizon schema version (bumped on breaking contract change).
HORIZON_SCHEMA_VERSION = 1

#: §25.7 Deadline — the four verbatim kinds, in plan order
#: (harness-provable).  snake_case per codebase convention.
DEADLINES: tuple[str, ...] = (
    "30_minutes",
    "2_hours",
    "8_hours",
    "until_completion",
)

#: §25.7 — the honest window per deadline kind, in seconds.
#: ``until_completion`` is unbounded: ``None`` means no deadline exists,
#: not a deadline that never arrives.
DEADLINE_SECONDS: dict[str, float | None] = {
    "30_minutes": 30.0 * 60.0,
    "2_hours": 2.0 * 60.0 * 60.0,
    "8_hours": 8.0 * 60.0 * 60.0,
    "until_completion": None,
}

#: §25.3 — the long-running state ladder (NEXUS-owned shapes for the
#: plan's «Long-running state»; the order is the ladder's order).
GOAL_STATES: tuple[str, ...] = (
    "pending",
    "running",
    "paused",
    "completed",
    "failed",
    "deadline_hit",
)

#: The transition law — where each state may go.  ``completed`` is
#: terminal: a finished goal is finished (resuming one is refused).
TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running"}),
    "running": frozenset({"paused", "completed", "failed", "deadline_hit"}),
    "paused": frozenset({"running"}),
    "completed": frozenset(),
    "failed": frozenset({"running"}),
    "deadline_hit": frozenset({"running"}),
}

#: States a resume may start from (the §22.4 spirit: from disk, never
#: from memory — a running state is resumable because the process that
#: wrote it may be dead; the generation lease proves who owns the run).
RESUMABLE_STATES: frozenset[str] = frozenset(
    {"paused", "failed", "deadline_hit", "running"}
)


# ------------------------------------------------------------------ errors


class HorizonError(Exception):
    """Long-horizon misuse or violated law."""


class UnknownDeadlineError(HorizonError):
    """A deadline outside the §25.7 four."""


class UnknownGoalError(HorizonError):
    """A goal id that was never persisted."""


class IllegalTransitionError(HorizonError):
    """A state change the §25.3 ladder does not allow."""


class BlindResumeError(HorizonError):
    """§25.6/§22.4 — the resume was refused: the evidence on disk does
    not support a safe continuation.  Carries every refusal reason."""

    def __init__(self, refusals: tuple[str, ...] | list[str]) -> None:
        self.refusals = tuple(refusals)
        super().__init__("blind resume refused — " + "; ".join(self.refusals))


def new_goal_id() -> str:
    """New goal identity: ``goal_`` + 12 hex chars (the house id family)."""
    return "goal_" + secrets.token_hex(6)


def deadline_seconds(kind: str) -> float | None:
    """The §25.7 window for a deadline kind (``None`` = unbounded)."""
    if kind not in DEADLINES:
        raise UnknownDeadlineError(
            f"unknown deadline {kind!r} — the §25.7 four are {DEADLINES}"
        )
    return DEADLINE_SECONDS[kind]


# ---------------------------------------------------------------- records


@dataclass(frozen=True, slots=True)
class GoalRecord:
    """One long-horizon goal, persisted verbatim.

    ``deadline_at`` is epoch seconds (a **wall** deadline must survive a
    reboot — a monotonic clock does not) or ``None`` for
    ``until_completion``.  ``progress_seq`` counts the completed steps;
    ``last_checkpoint_id`` names the newest §22 checkpoint (when a
    manager is wired); ``generation`` is the durable run lease — the
    newest runner owns the goal, a superseded runner retires itself.
    """

    goal_id: str
    statement: str
    deadline: str
    state: str = "pending"
    created_at: str = ""
    updated_at: str = ""
    progress_seq: int = 0
    last_checkpoint_id: str | None = None
    generation: int = 0
    deadline_at: float | None = None

    def __post_init__(self) -> None:
        if not self.goal_id.strip():
            raise HorizonError("goal_id must be non-empty")
        if not self.statement.strip():
            raise HorizonError("the goal statement must be non-empty")
        if self.deadline not in DEADLINES:
            raise UnknownDeadlineError(
                f"unknown deadline {self.deadline!r} — the §25.7 four are"
                f" {DEADLINES}"
            )
        if self.state not in GOAL_STATES:
            raise HorizonError(
                f"unknown state {self.state!r} — the ladder is {GOAL_STATES}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": HORIZON_SCHEMA_VERSION,
            "goal_id": self.goal_id,
            "statement": self.statement,
            "deadline": self.deadline,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "progress_seq": self.progress_seq,
            "last_checkpoint_id": self.last_checkpoint_id,
            "generation": self.generation,
            "deadline_at": self.deadline_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalRecord:
        return cls(
            goal_id=str(data["goal_id"]),
            statement=str(data["statement"]),
            deadline=str(data["deadline"]),
            state=str(data.get("state") or "pending"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            progress_seq=int(data.get("progress_seq") or 0),
            last_checkpoint_id=data.get("last_checkpoint_id"),
            generation=int(data.get("generation") or 0),
            deadline_at=(
                float(data["deadline_at"])
                if data.get("deadline_at") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ProgressNote:
    """One line of the long-run journal — strictly monotonic seq."""

    seq: int
    ts: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "ts": self.ts, "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgressNote:
        return cls(
            seq=int(data["seq"]),
            ts=str(data.get("ts") or ""),
            message=str(data.get("message") or ""),
        )


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """What one step reports back: keep going, or the goal is done.

    ``done=True`` is the step's claim of completion — the runner
    records it honestly; everything else (exceptions, deadlines) stops
    the run with the true state.
    """

    done: bool
    note: str = ""


#: A horizon step: (steps_done_so_far, current record) → outcome.
#: The step is the user's work unit — long by definition (minutes+);
#: the deadline is enforced at step granularity (documented decision:
#: a cooperative runner cannot preempt a step mid-flight).
StepFn = Callable[[int, GoalRecord], StepOutcome]
