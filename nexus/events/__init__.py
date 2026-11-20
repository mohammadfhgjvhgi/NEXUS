"""NEXUS Event Bus package (Final Build Plan §2.2)."""

from .bus import EventBus, EventHandler, Subscription
from .types import (
    CANONICAL_EVENTS,
    EVENT_CATEGORIES,
    DispatchResult,
    Event,
    EventError,
    EventName,
    utc_now_iso,
)

__all__ = [
    "CANONICAL_EVENTS",
    "EVENT_CATEGORIES",
    "DispatchResult",
    "Event",
    "EventBus",
    "EventError",
    "EventHandler",
    "EventName",
    "Subscription",
    "utc_now_iso",
]
