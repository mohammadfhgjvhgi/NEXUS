"""NEXUS Task Engine package (Final Build Plan §2.4).

This package ``__init__`` deliberately exports **states only**:
``nexus.core.session.models`` imports the vocabulary from
``.states``, while ``machine`` imports models — re-exporting
``machine`` here would create a circular import. Import the engine
directly::

    from nexus.core.engine.machine import TaskEngine
"""

from .states import (
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransitionError,
    TaskState,
    TransitionRecord,
    can_transition,
)

__all__ = [
    "TERMINAL_STATES",
    "TRANSITIONS",
    "InvalidTransitionError",
    "TaskState",
    "TransitionRecord",
    "can_transition",
]
