"""Task State Machine — states and transition table (Final Build Plan §2.4).

Thirteen states, verbatim::

    CREATED → ANALYZING → CLARIFICATION_REQUIRED → PLANNING → EXECUTING
    → VERIFYING → REPAIRING → WAITING_NETWORK → WAITING_RESOURCE
    → RECOVERING → PAUSED → COMPLETED / CANCELLED

Transition rules (documented rationale):

* ``CREATED``          → ANALYZING (start) or CANCELLED.
* ``ANALYZING``        → PLANNING, CLARIFICATION_REQUIRED, PAUSED, CANCELLED.
* ``CLARIFICATION_REQUIRED`` → ANALYZING (re-analyze), PLANNING (clarified),
  PAUSED, CANCELLED.
* ``PLANNING``         → EXECUTING, PAUSED, CANCELLED.
* ``EXECUTING``        → VERIFYING, REPAIRING, WAITING_NETWORK,
  WAITING_RESOURCE, RECOVERING, PAUSED, CANCELLED.
* ``VERIFYING``        → COMPLETED, REPAIRING, PAUSED, CANCELLED.
* ``REPAIRING``        → EXECUTING (retry), VERIFYING, PAUSED, CANCELLED.
* ``WAITING_NETWORK``  → EXECUTING (available again), RECOVERING, PAUSED,
  CANCELLED.
* ``WAITING_RESOURCE`` → EXECUTING, RECOVERING, PAUSED, CANCELLED.
* ``RECOVERING``       → EXECUTING, VERIFYING, WAITING_RESOURCE, PAUSED,
  CANCELLED.
* ``PAUSED``           → any pausable-from state (resume) or CANCELLED.
* ``COMPLETED`` / ``CANCELLED`` → terminal, no outgoing transitions.

Design notes:

* Completion is only reachable through VERIFYING — verification-first is
  a core NEXUS principle (Spec). Cancellation is reachable from every
  non-terminal state.
* ``_RESUME_TARGETS`` excludes ``CREATED``: a task can never be paused in
  CREATED (its only exits are ANALYZING/CANCELLED), so resuming into it
  would be a rewind, not a resume. Explicit ``resume(target=…))`` may
  still jump between pausable states — the caller owns that decision.
* Asymmetry: ``WAITING_NETWORK → RECOVERING`` exists (a network stall can
  escalate to recovery) while the reverse is not needed — recovery lands
  on ``WAITING_RESOURCE`` or ``EXECUTING`` instead (the EXECUTING hub).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TaskState(StrEnum):
    """Task states (Final Build Plan §2.4) — verbatim, 13 states."""

    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    WAITING_NETWORK = "WAITING_NETWORK"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    RECOVERING = "RECOVERING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.CANCELLED}
)

#: States a paused task may resume into: every non-terminal state except
#: CREATED (a task can never be paused in CREATED — see design notes).
_RESUME_TARGETS: frozenset[TaskState] = frozenset(
    state
    for state in TaskState
    if state not in TERMINAL_STATES
    and state is not TaskState.PAUSED
    and state is not TaskState.CREATED
)

TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.ANALYZING, TaskState.CANCELLED}),
    TaskState.ANALYZING: frozenset(
        {
            TaskState.CLARIFICATION_REQUIRED,
            TaskState.PLANNING,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.CLARIFICATION_REQUIRED: frozenset(
        {
            TaskState.ANALYZING,
            TaskState.PLANNING,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.PLANNING: frozenset(
        {TaskState.EXECUTING, TaskState.PAUSED, TaskState.CANCELLED}
    ),
    TaskState.EXECUTING: frozenset(
        {
            TaskState.VERIFYING,
            TaskState.REPAIRING,
            TaskState.WAITING_NETWORK,
            TaskState.WAITING_RESOURCE,
            TaskState.RECOVERING,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.VERIFYING: frozenset(
        {
            TaskState.COMPLETED,
            TaskState.REPAIRING,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.REPAIRING: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.VERIFYING,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING_NETWORK: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.RECOVERING,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.WAITING_RESOURCE: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.RECOVERING,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.RECOVERING: frozenset(
        {
            TaskState.EXECUTING,
            TaskState.VERIFYING,
            TaskState.WAITING_RESOURCE,
            TaskState.PAUSED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.PAUSED: _RESUME_TARGETS | {TaskState.CANCELLED},
    TaskState.COMPLETED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a transition is not allowed by the state machine."""

    def __init__(self, from_state: TaskState, to_state: TaskState) -> None:
        allowed = ", ".join(sorted(s.value for s in TRANSITIONS[from_state])) or "none"
        super().__init__(
            f"invalid task transition {from_state.value} → {to_state.value} "
            f"(allowed from {from_state.value}: {allowed})"
        )
        self.from_state = from_state
        self.to_state = to_state


def can_transition(from_state: TaskState, to_state: TaskState) -> bool:
    return to_state in TRANSITIONS[from_state]


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    """One applied transition, kept in Task.state_history (audit trail)."""

    from_state: TaskState
    to_state: TaskState
    at: datetime
    reason: str | None = None
    session_id: str | None = None
