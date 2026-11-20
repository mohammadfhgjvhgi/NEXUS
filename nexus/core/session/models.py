"""Session system entities (Final Build Plan §2.3).

Hierarchy — strictly separated, never mixed:

    User
     └── Conversation
          └── Task
               └── Session

* **User**        — the human operator identity.
* **Conversation**— a dialogue container (many tasks may share it).
* **Task**        — one unit of work with its own state machine.
* **Session**     — one continuous execution segment of a task; a new
  session is opened every time NEXUS (re)opens a task, which is exactly
  how the §2.6 exit criteria keep state continuity across restarts.

Id prefixes: ``usr_`` ``conv_`` ``task_`` ``sess_`` (+ ``step_`` for plan
steps, ``ckpt_`` for checkpoints) — each identity is distinct by design.

نظام الجلسات — أربعة كيانات متمايزة في هرمية صارمة بلا خلط.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..engine.states import TaskState, TransitionRecord


def new_id(prefix: str) -> str:
    """New prefixed identity (uuid4 hex)."""
    return f"{prefix}_{uuid.uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class SessionError(Exception):
    """Session/conversation/task hierarchy misuse."""


# --------------------------------------------------------------------- User


@dataclass(slots=True)
class User:
    id: str
    display_name: str
    created_at: datetime

    @classmethod
    def create(cls, *, display_name: str = "User", user_id: str | None = None) -> User:
        return cls(
            id=user_id or new_id("usr"),
            display_name=display_name,
            created_at=utc_now(),
        )


# ------------------------------------------------------------- Conversation


@dataclass(slots=True)
class Conversation:
    id: str
    user_id: str
    title: str
    created_at: datetime
    task_ids: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls, *, user_id: str, title: str = "Conversation", conversation_id: str | None = None
    ) -> Conversation:
        return cls(
            id=conversation_id or new_id("conv"),
            user_id=user_id,
            title=title,
            created_at=utc_now(),
        )

    def add_task(self, task_id: str) -> None:
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)


# ------------------------------------------------------------------ Session


@dataclass(slots=True)
class Session:
    id: str
    task_id: str
    index: int  # 1-based position within the task
    started_at: datetime
    ended_at: datetime | None = None
    context: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    @classmethod
    def begin(
        cls, *, task_id: str, index: int, context: Mapping[str, Any] | None = None
    ) -> Session:
        return cls(
            id=new_id("sess"),
            task_id=task_id,
            index=index,
            started_at=utc_now(),
            context=dict(context or {}),
        )

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def end(self, *, notes: str | None = None) -> None:
        if self.ended_at is None:
            self.ended_at = utc_now()
        if notes is not None:
            self.notes = notes


# --------------------------------------------------------------------- Plan


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class PlanStep:
    id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    agent: str | None = None

    @classmethod
    def create(cls, description: str, *, agent: str | None = None) -> PlanStep:
        return cls(id=new_id("step"), description=description, agent=agent)


@dataclass(slots=True)
class TaskPlan:
    steps: list[PlanStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    notes: str | None = None

    @classmethod
    def empty(cls) -> TaskPlan:
        return cls()

    @classmethod
    def from_steps(cls, descriptions: Iterable[str]) -> TaskPlan:
        return cls(steps=[PlanStep.create(description) for description in descriptions])


# -------------------------------------------------------------- Checkpoints


@dataclass(slots=True)
class CheckpointRef:
    """Light checkpoint reference — the Recovery Engine (later phase)
    owns the real checkpoint store; tasks keep references only."""

    id: str
    created_at: datetime
    reason: str
    path: str | None = None
    session_id: str | None = None

    @classmethod
    def create(
        cls, *, reason: str, path: str | None = None, session_id: str | None = None
    ) -> CheckpointRef:
        return cls(
            id=new_id("ckpt"),
            created_at=utc_now(),
            reason=reason,
            path=path,
            session_id=session_id,
        )


# ------------------------------------------------------------------- Errors


@dataclass(slots=True)
class TaskError:
    code: str
    message: str
    at: datetime
    fatal: bool = False
    source: str | None = None

    @classmethod
    def create(
        cls, *, code: str, message: str, fatal: bool = False, source: str | None = None
    ) -> TaskError:
        return cls(code=code, message=message, at=utc_now(), fatal=fatal, source=source)


# ------------------------------------------------------- Verification record


class VerificationStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class VerificationCheck:
    name: str
    passed: bool
    detail: str | None = None
    at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class VerificationRecord:
    """Light verification record — the Verification Engine (later phase)
    owns evidence-based acceptance; tasks keep the summary record."""

    status: VerificationStatus = VerificationStatus.PENDING
    checks: list[VerificationCheck] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def create(cls) -> VerificationRecord:
        return cls()


# ------------------------------------------------------------------- Result


@dataclass(slots=True)
class TaskResult:
    summary: str
    artifacts: list[str] = field(default_factory=list)
    completed_at: datetime | None = None
    success: bool = True


# --------------------------------------------------------------------- Task

#: Scope placeholder mapping — structured by the Scope Engine (Phase 2,
#: Plan §3): :meth:`nexus.core.scope.models.Scope.to_scope_map` produces
#: this canonical mapping with the six §3.2 dimension keys. Kept as a
#: plain mapping so persistence stays stable.
ScopeMap = dict[str, Any]


@dataclass(slots=True)
class Task:
    """One unit of work — persists exactly the §2.5 fields (plus
    bookkeeping: sessions, state history, timestamps)."""

    # §2.5 persisted fields (verbatim)
    id: str
    conversation_id: str
    goal: str
    prompt: str
    scope: ScopeMap = field(default_factory=dict)
    workspace: str = "main"
    plan: TaskPlan = field(default_factory=TaskPlan)
    agents: list[str] = field(default_factory=list)
    state: TaskState = TaskState.CREATED
    checkpoints: list[CheckpointRef] = field(default_factory=list)
    errors: list[TaskError] = field(default_factory=list)
    verification: VerificationRecord = field(default_factory=VerificationRecord)
    result: TaskResult | None = None

    # bookkeeping
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    sessions: list[Session] = field(default_factory=list)
    state_history: list[TransitionRecord] = field(default_factory=list)
    state_before_pause: TaskState | None = None

    @classmethod
    def create(
        cls,
        *,
        conversation_id: str,
        goal: str,
        prompt: str,
        scope: Mapping[str, Any] | None = None,
        workspace: str = "main",
        plan: TaskPlan | None = None,
        agents: Iterable[str] | None = None,
        task_id: str | None = None,
    ) -> Task:
        return cls(
            id=task_id or new_id("task"),
            conversation_id=conversation_id,
            goal=goal,
            prompt=prompt,
            scope=dict(scope or {}),
            workspace=workspace,
            plan=plan if plan is not None else TaskPlan.empty(),
            agents=list(agents or []),
        )

    def touch(self) -> None:
        self.updated_at = utc_now()

    @property
    def active_session(self) -> Session | None:
        for session in reversed(self.sessions):
            if session.is_active:
                return session
        return None

    def apply_transition(
        self,
        to_state: TaskState,
        *,
        reason: str | None = None,
        session_id: str | None = None,
    ) -> TransitionRecord:
        """Record one transition (called by the TaskEngine only)."""
        record = TransitionRecord(
            from_state=self.state,
            to_state=to_state,
            at=utc_now(),
            reason=reason,
            session_id=session_id,
        )
        self.state = to_state
        self.state_history.append(record)
        self.touch()
        return record
