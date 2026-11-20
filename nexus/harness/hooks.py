"""Harness lifecycle hooks (Plan §7.1/§7.2 — the ECC + Cline hook pattern).

ECC wires JSON-declared hooks around its commands; the Cline SDK
exposes a hooks surface on its stateful core. NEXUS adapts the
*pattern* with an eight-point synchronous registry:

=================  ============================================  ============
Point              Fires                                          Veto?
=================  ============================================  ============
``session_start``  an agent session enters ACTIVE                 no
``session_end``    an agent session closes                        no
``task_start``     bus: task.started                              no
``task_end``       bus: task.completed                            no
``agent_start``    bus: agent.started                             no
``agent_end``      bus: agent.completed / agent.failed            no
``pre_tool_call``  the §6.2 loop, before a tool dispatches       **yes**
``post_tool_call`` the loop after the tool returns (or fails)     no
=================  ============================================  ============

The bus-driven points bind to the 28 canonical §2.2 events only —
``bind_bus`` subscribes with existing names, and the event-name guard
stays binding. The two tool points are invoked by the loop itself
(the loop owns the dispatch seam), where a ``pre_tool_call`` handler
returning ``False`` vetoes the call (the model observes the veto as
an ordinary observation — coordination, not crash).

Handlers are ``Callable[[HookContext], bool | None]``; a raising
handler is caught and logged unless ``strict`` (then it propagates).
طبقة الخطاطيف — ثمانية نقاط التزام، ونقض قبل استدعاء الأداة فقط.

Stdlib only.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..events import Event, EventBus, EventName

logger = logging.getLogger("nexus.harness")

#: The eight hook points (harness-provable, fixed vocabulary).
HOOK_POINTS: tuple[str, ...] = (
    "session_start",
    "session_end",
    "task_start",
    "task_end",
    "agent_start",
    "agent_end",
    "pre_tool_call",
    "post_tool_call",
)

#: Hook points whose handlers may veto (return ``False`` → blocked).
VETO_POINTS: frozenset[str] = frozenset({"pre_tool_call"})

Handler = Callable[["HookContext"], "bool | None"]


@dataclass(slots=True)
class HookContext:
    """What a handler sees: the point, the actor and the payload."""

    point: str
    agent_id: str = ""
    task_id: str = ""
    tool: str = ""
    arguments: Mapping[str, Any] = field(default_factory=dict)
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "point": self.point,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "detail": dict(self.detail),
        }


class HarnessHooks:
    """The synchronous hook registry (Plan §7.1/§7.2 pattern).

    * ``register(point, handler)`` — one handler per (point, handler);
    * ``fire(point, context)`` — runs handlers in registration order;
      returns ``False`` only for veto points whose handler returned
      ``False`` (the call is blocked), else ``True``;
    * ``bind_bus(bus)`` — the event-driven points fire from real §2.2
      events (no invented names, the guard stays binding);
    * a raising handler is logged — or propagates when ``strict``.
    """

    def __init__(self, *, strict: bool = False) -> None:
        self._strict = strict
        self._handlers: dict[str, list[Handler]] = {p: [] for p in HOOK_POINTS}
        self._bound_bus: EventBus | None = None

    # ------------------------------------------------------------- roster

    def register(self, point: str, handler: Handler) -> None:
        if point not in HOOK_POINTS:
            raise ValueError(f"unknown hook point {point!r} (have: {HOOK_POINTS})")
        if handler not in self._handlers[point]:
            self._handlers[point].append(handler)

    def unregister(self, point: str, handler: Handler) -> bool:
        if point not in self._handlers:
            return False
        try:
            self._handlers[point].remove(handler)
            return True
        except ValueError:
            return False

    def count(self, point: str | None = None) -> int:
        if point is None:
            return sum(len(v) for v in self._handlers.values())
        return len(self._handlers.get(point, ()))

    # ---------------------------------------------------------------- fire

    def fire(self, point: str, context: HookContext) -> bool:
        """Run the handlers for one point.

        Returns ``False`` only when a veto-point handler blocked the
        action; any other outcome (including handler errors in
        non-strict mode) returns ``True`` — hooks notify, they do not
        stall the loop.
        """
        if point not in self._handlers:
            raise ValueError(f"unknown hook point {point!r}")
        allowed = True
        for handler in list(self._handlers[point]):
            try:
                verdict = handler(context)
            except Exception:  # noqa: BLE001 — a hook never kills the loop
                if self._strict:
                    raise
                logger.exception("hook %s handler failed — logged, loop continues", point)
                continue
            if verdict is False and point in VETO_POINTS:
                allowed = False
        return allowed

    # ------------------------------------------------------------- binding

    def bind_bus(self, bus: EventBus) -> None:
        """Bind the event-driven points to the canonical bus events.

        Subscribes with existing §2.2 names only; payloads ride the
        event payload, the handler context carries ids verbatim.
        """
        if self._bound_bus is bus:
            return

        def _emit(point: str) -> Callable[[Event], None]:
            def handler(event: Event) -> None:
                context = HookContext(
                    point=point,
                    agent_id=str(event.payload.get("agent_id", "")),
                    task_id=str(event.task_id or event.payload.get("task_id", "")),
                    detail=dict(event.payload),
                )
                self.fire(point, context)

            return handler

        subscriptions: list[tuple[EventName, str]] = [
            (EventName.TASK_STARTED, "task_start"),
            (EventName.TASK_COMPLETED, "task_end"),
            (EventName.AGENT_STARTED, "agent_start"),
            (EventName.AGENT_COMPLETED, "agent_end"),
            (EventName.AGENT_FAILED, "agent_end"),
        ]
        for event, point in subscriptions:
            bus.subscribe(event.value, _emit(point))
        self._bound_bus = bus
