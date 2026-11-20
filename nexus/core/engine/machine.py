"""Task Engine — the state machine driver (Final Build Plan §2.4).

The engine owns every state transition: it validates against the table in
:mod:`.states`, records the audit trail on the task, and publishes the
matching canonical event (``task.started`` / ``task.updated`` /
``task.paused`` / ``task.resumed`` / ``task.completed``).

Event selection rule:

* target PAUSED            → ``task.paused``
* target CANCELLED         → ``task.updated`` (there is no ``task.cancelled``
  in the §2.2 registry; a paused→cancel must NOT look like a resume)
* resumed (from PAUSED)    → ``task.resumed``
* target COMPLETED         → ``task.completed``
* any other transition     → ``task.updated``
* CREATED → ANALYZING      → ``task.started`` (via :meth:`TaskEngine.start`)

Phase 1 concurrency note: the engine (and the session manager) are
single-threaded by design; only the Event Bus is thread-safe.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...events import EventBus, EventName
from ..session.models import Task, TaskError, TaskResult, utc_now
from .states import (
    TERMINAL_STATES,
    InvalidTransitionError,
    TaskState,
    can_transition,
)


class TaskEngine:
    """Drives the Task State Machine (Plan §2.4)."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    # ------------------------------------------------------------ lifecycle

    def start(
        self,
        task: Task,
        *,
        session_id: str | None = None,
        reason: str = "task started",
    ) -> Task:
        """CREATED → ANALYZING; publishes ``task.started``."""
        if task.state is not TaskState.CREATED:
            raise InvalidTransitionError(task.state, TaskState.ANALYZING)
        self._apply(task, TaskState.ANALYZING, reason, session_id,
                    event=EventName.TASK_STARTED)
        return task

    def transition(
        self,
        task: Task,
        to_state: TaskState | str,
        *,
        reason: str | None = None,
        session_id: str | None = None,
    ) -> Task:
        """Generic validated transition; publishes ``task.updated``
        (or the specific pause/resume/complete event)."""
        target = to_state if isinstance(to_state, TaskState) else TaskState(to_state)
        if not can_transition(task.state, target):
            raise InvalidTransitionError(task.state, target)
        self._apply(task, target, reason, session_id)
        return task

    def pause(
        self,
        task: Task,
        *,
        reason: str | None = "paused",
        session_id: str | None = None,
    ) -> Task:
        return self.transition(task, TaskState.PAUSED, reason=reason,
                               session_id=session_id)

    def resume(
        self,
        task: Task,
        *,
        target: TaskState | str | None = None,
        reason: str | None = "resumed",
        session_id: str | None = None,
    ) -> Task:
        """Resume from PAUSED — defaults to the state before pausing
        (falls back to EXECUTING)."""
        if task.state is not TaskState.PAUSED:
            raise InvalidTransitionError(task.state, TaskState.EXECUTING)
        goal_state = (
            target
            if target is not None
            else task.state_before_pause or TaskState.EXECUTING
        )
        goal = (
            goal_state
            if isinstance(goal_state, TaskState)
            else TaskState(goal_state)
        )
        return self.transition(task, goal, reason=reason, session_id=session_id)

    def complete(
        self,
        task: Task,
        *,
        summary: str,
        artifacts: Iterable[str] | None = None,
        success: bool = True,
        reason: str = "all verification checks passed",
        session_id: str | None = None,
    ) -> Task:
        """VERIFYING → COMPLETED; attaches the result; publishes
        ``task.completed``."""
        if not can_transition(task.state, TaskState.COMPLETED):
            raise InvalidTransitionError(task.state, TaskState.COMPLETED)
        task.result = TaskResult(
            summary=summary,
            artifacts=list(artifacts or []),
            completed_at=utc_now(),
            success=success,
        )
        self._apply(task, TaskState.COMPLETED, reason, session_id,
                    event=EventName.TASK_COMPLETED)
        return task

    def cancel(
        self,
        task: Task,
        *,
        reason: str = "cancelled by user",
        session_id: str | None = None,
    ) -> Task:
        """Any non-terminal state → CANCELLED."""
        if task.state in TERMINAL_STATES:
            raise InvalidTransitionError(task.state, TaskState.CANCELLED)
        return self.transition(task, TaskState.CANCELLED, reason=reason,
                               session_id=session_id)

    # ---------------------------------------------------------------- errors

    def record_error(
        self,
        task: Task,
        *,
        code: str,
        message: str,
        fatal: bool = False,
        source: str | None = None,
    ) -> TaskError:
        """Append an error record to the task (§2.5 errors field)."""
        error = TaskError.create(code=code, message=message, fatal=fatal,
                                 source=source)
        task.errors.append(error)
        task.touch()
        return error

    # -------------------------------------------------------------- internal

    def _apply(
        self,
        task: Task,
        target: TaskState,
        reason: str | None,
        session_id: str | None,
        event: EventName | None = None,
    ) -> None:
        if target is TaskState.PAUSED:
            task.state_before_pause = task.state
        elif task.state is TaskState.PAUSED:
            task.state_before_pause = None
        task.apply_transition(target, reason=reason, session_id=session_id)
        if event is None:
            if target is TaskState.COMPLETED:
                event = EventName.TASK_COMPLETED
            elif target is TaskState.PAUSED:
                event = EventName.TASK_PAUSED
            elif target is TaskState.CANCELLED:
                # no "task.cancelled" in the §2.2 registry — and a
                # paused→cancel must never look like a resume
                event = EventName.TASK_UPDATED
            else:
                previous = (
                    task.state_history[-1].from_state
                    if task.state_history
                    else task.state
                )
                event = (
                    EventName.TASK_RESUMED
                    if previous is TaskState.PAUSED
                    else EventName.TASK_UPDATED
                )
        payload = {
            "from": (
                task.state_history[-1].from_state.value
                if task.state_history
                else task.state.value
            ),
            "to": target.value,
        }
        if reason is not None:
            payload["reason"] = reason
        self._bus.publish(
            event,
            payload=payload,
            task_id=task.id,
            conversation_id=task.conversation_id,
            session_id=session_id,
            source="nexus.engine",
        )
