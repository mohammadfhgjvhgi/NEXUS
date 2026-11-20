"""NEXUS Event Bus — canonical event types (Final Build Plan §2.2).

The 28 canonical event names below are verbatim from the plan. They form the
documented baseline vocabulary of the platform. Future modules may publish
additional dotted names; the bus keeps this registry as the reference set
and can enforce it in strict mode (``EventBus(strict_names=True))``).

مفردات الأحداث المعيارية الـ28 — طبقة الأحداث المركزية للمنصة.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventName(StrEnum):
    """Canonical event names (Final Build Plan §2.2) — verbatim."""

    # system
    SYSTEM_STARTED = "system.started"

    # task lifecycle
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_UPDATED = "task.updated"
    TASK_PAUSED = "task.paused"
    TASK_RESUMED = "task.resumed"
    TASK_COMPLETED = "task.completed"

    # agents
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # tools
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # models
    MODEL_LOADING = "model.loading"
    MODEL_LOADED = "model.loaded"
    MODEL_UNLOADED = "model.unloaded"
    MODEL_ERROR = "model.error"

    # windows
    WINDOW_OPENED = "window.opened"
    WINDOW_CLOSED = "window.closed"

    # checkpoints / recovery
    CHECKPOINT_CREATED = "checkpoint.created"
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_COMPLETED = "recovery.completed"

    # verification
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"

    # memory / learning
    MEMORY_CREATED = "memory.created"
    MEMORY_UPDATED = "memory.updated"
    LEARNING_CREATED = "learning.created"


CANONICAL_EVENTS: frozenset[str] = frozenset(member.value for member in EventName)

#: Documentation map: category → its canonical events (Plan §2.2 grouping).
EVENT_CATEGORIES: Mapping[str, tuple[EventName, ...]] = {
    "system": (EventName.SYSTEM_STARTED,),
    "task": (
        EventName.TASK_CREATED,
        EventName.TASK_STARTED,
        EventName.TASK_UPDATED,
        EventName.TASK_PAUSED,
        EventName.TASK_RESUMED,
        EventName.TASK_COMPLETED,
    ),
    "agent": (
        EventName.AGENT_STARTED,
        EventName.AGENT_COMPLETED,
        EventName.AGENT_FAILED,
    ),
    "tool": (
        EventName.TOOL_CALLED,
        EventName.TOOL_COMPLETED,
        EventName.TOOL_FAILED,
    ),
    "model": (
        EventName.MODEL_LOADING,
        EventName.MODEL_LOADED,
        EventName.MODEL_UNLOADED,
        EventName.MODEL_ERROR,
    ),
    "window": (EventName.WINDOW_OPENED, EventName.WINDOW_CLOSED),
    "checkpoint": (EventName.CHECKPOINT_CREATED,),
    "recovery": (
        EventName.RECOVERY_STARTED,
        EventName.RECOVERY_COMPLETED,
    ),
    "verification": (
        EventName.VERIFICATION_STARTED,
        EventName.VERIFICATION_PASSED,
        EventName.VERIFICATION_FAILED,
    ),
    "memory": (EventName.MEMORY_CREATED, EventName.MEMORY_UPDATED),
    "learning": (EventName.LEARNING_CREATED,),
}


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable, serializable event envelope.

    ``payload`` is treated as read-only by convention; ``to_dict`` returns a
    plain copy. Correlation ids are optional context links (task /
    conversation / session).
    """

    name: str
    sequence: int
    timestamp: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    source: str | None = None
    task_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }
        for key in ("source", "task_id", "conversation_id", "session_id"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Event:
        """Rebuild an event from its serialized form (checkpoints/replay)."""
        return cls(
            name=str(data["name"]),
            sequence=int(data["sequence"]),
            timestamp=str(data["timestamp"]),
            payload=dict(data.get("payload") or {}),
            source=data.get("source"),
            task_id=data.get("task_id"),
            conversation_id=data.get("conversation_id"),
            session_id=data.get("session_id"),
        )


@dataclass(frozen=True, slots=True)
class EventError:
    """A subscriber failure captured during dispatch (isolation by design)."""

    handler: str
    error_type: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "handler": self.handler,
            "error_type": self.error_type,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Outcome of one publish: how many handlers ran, which failed."""

    event: Event
    handler_count: int
    errors: tuple[EventError, ...] = ()

    @property
    def delivered(self) -> bool:
        """True when at least one handler ran and none failed."""
        return self.handler_count > 0 and not self.errors
