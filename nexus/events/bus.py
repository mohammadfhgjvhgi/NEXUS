"""Central Event Bus (Final Build Plan §2.2).

Publish/subscribe hub for the whole platform. Design rules:

* Thread-safe (one RLock guards subscriptions, sequence, history).
* Handler isolation: a raising subscriber never breaks dispatch — the
  failure is captured as :class:`EventError` and logged.
* Subscriptions match by exact name, by category prefix (``task.*``) or
  by the global wildcard ``*``. No other wildcard shapes are allowed.
* Bounded in-memory history (ring buffer) for replay/audit; persistence
  of the stream is a later-phase concern (checkpoints/logs own it).
* ``strict_names=True`` rejects any name outside the 28 canonical events
  (useful in verification); the default is permissive for future modules.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any

from .types import (
    CANONICAL_EVENTS,
    DispatchResult,
    Event,
    EventError,
    EventName,
    utc_now_iso,
)

logger = logging.getLogger("nexus.events")

EventHandler = Callable[[Event], None]


def _matches(pattern: str, name: str) -> bool:
    """Match an event name against a subscription pattern."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return name.startswith(pattern[:-1])  # "task.*" → prefix "task."
    return pattern == name


def _validate_pattern(pattern: str) -> None:
    if not pattern or not pattern.strip():
        raise ValueError("subscription pattern must be a non-empty string")
    if "*" in pattern:
        if pattern == "*":
            return
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if not prefix or "*" in prefix:
                raise ValueError(f"invalid wildcard pattern: {pattern!r}")
            return
        raise ValueError(
            "patterns allow only the global '*' or a trailing '.*' "
            f"(e.g. 'task.*'); got {pattern!r}"
        )


class Subscription:
    """One active subscription (identity-based equality)."""

    __slots__ = ("id", "pattern", "handler", "once")

    def __init__(self, sub_id: int, pattern: str, handler: EventHandler, once: bool) -> None:
        self.id = sub_id
        self.pattern = pattern
        self.handler = handler
        self.once = once

    def matches(self, name: str) -> bool:
        return _matches(self.pattern, name)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"Subscription(id={self.id}, pattern={self.pattern!r}, "
            f"handler={self.handler!r}, once={self.once})"
        )


class EventBus:
    """Central, thread-safe publish/subscribe bus (Plan §2.2)."""

    def __init__(
        self, *, history_size: int = 1000, strict_names: bool = False
    ) -> None:
        if history_size < 0:
            raise ValueError("history_size must be >= 0")
        self._lock = threading.RLock()
        self._subscriptions: dict[int, Subscription] = {}
        self._next_subscription_id = 1
        self._sequence = 0
        self._published_count = 0
        self._history: deque[Event] = deque(maxlen=history_size)
        self._strict_names = strict_names

    # ------------------------------------------------------------------ state

    @property
    def strict_names(self) -> bool:
        return self._strict_names

    @property
    def published_count(self) -> int:
        with self._lock:
            return self._published_count

    @property
    def subscription_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    # ---------------------------------------------------------- subscriptions

    def subscribe(
        self, pattern: str, handler: EventHandler, *, once: bool = False
    ) -> Subscription:
        """Register a handler for ``pattern`` (exact, ``prefix.*`` or ``*``)."""
        _validate_pattern(pattern)
        if not callable(handler):
            raise TypeError("handler must be callable")
        with self._lock:
            subscription = Subscription(
                self._next_subscription_id, pattern, handler, once
            )
            self._next_subscription_id += 1
            self._subscriptions[subscription.id] = subscription
            return subscription

    def unsubscribe(self, subscription: Subscription) -> bool:
        """Remove a subscription. Returns True when it was still active."""
        with self._lock:
            return self._subscriptions.pop(subscription.id, None) is not None

    # ------------------------------------------------------------- publishing

    def publish(
        self,
        name: str | EventName,
        *,
        payload: Mapping[str, Any] | None = None,
        source: str | None = None,
        task_id: str | None = None,
        conversation_id: str | None = None,
        session_id: str | None = None,
    ) -> DispatchResult:
        """Build and dispatch one event; returns the dispatch outcome."""
        event_name = name.value if isinstance(name, EventName) else str(name)
        if self._strict_names and event_name not in CANONICAL_EVENTS:
            raise ValueError(f"unknown event name (strict mode): {event_name!r}")
        with self._lock:
            self._sequence += 1
            self._published_count += 1
            event = Event(
                name=event_name,
                sequence=self._sequence,
                timestamp=utc_now_iso(),
                payload=dict(payload or {}),
                source=source,
                task_id=task_id,
                conversation_id=conversation_id,
                session_id=session_id,
            )
            self._history.append(event)
            targets = [
                sub
                for sub in self._subscriptions.values()
                if sub.matches(event_name)
            ]
            for sub in targets:
                if sub.once:
                    self._subscriptions.pop(sub.id, None)
        return self._dispatch(event, targets)

    # --------------------------------------------------------------- history

    def history_snapshot(self, pattern: str | None = None) -> list[Event]:
        """Copy of the bounded history, optionally filtered by pattern."""
        with self._lock:
            events = list(self._history)
        if pattern is None:
            return events
        _validate_pattern(pattern)
        return [event for event in events if _matches(pattern, event.name)]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    # -------------------------------------------------------------- dispatch

    def _dispatch(self, event: Event, targets: list[Subscription]) -> DispatchResult:
        errors: list[EventError] = []
        for subscription in targets:
            try:
                subscription.handler(event)
            except Exception as exc:  # handler isolation: never propagate
                error = EventError(
                    handler=repr(subscription.handler),
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
                errors.append(error)
                logger.error(
                    "event handler failed (event=%s handler=%s): %s: %s",
                    event.name,
                    error.handler,
                    error.error_type,
                    error.message,
                )
        return DispatchResult(
            event=event, handler_count=len(targets), errors=tuple(errors)
        )
