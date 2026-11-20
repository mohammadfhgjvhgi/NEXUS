"""Window Manager façade (Final Build Plan §10 — the composer).

The idea the whole phase serves (the operator's own words):

    أنت تستخدم جهازك وNEXUS يعمل في مكان آخر في نفس الوقت.
    — you use your machine while NEXUS works somewhere else on it.

:class:`WindowManager` composes the five §10 modules over the §9.1
Computer API:

* :mod:`registry`    (§10.1) — the nine-field records,
  :meth:`sync` reconciles them with the live desktop and publishes
  the canonical ``window.opened`` / ``window.closed`` events;
* :mod:`ownership`   (§10.2) — USER / NEXUS / SHARED per window;
* :mod:`arbitration` (§10.3) — the per-window input verdicts,
  :meth:`hook` installs them as a Phase-6 ``pre_tool_call`` veto;
* :mod:`monitors`    (§10.4) — the monitor topology + placement;
* :mod:`overlay`     (§10.5) — "NEXUS is working / [Pause] [Resume]",
  :meth:`begin` / :meth:`pause` / :meth:`resume` / :meth:`end`.

Real effects still route through the §8.2 router (the manager is
policy and bookkeeping); the task binding (``task_id`` /
``workspace`` / ``agent``) is stamped onto every NEXUS claim so two
agents never fight over one window.

مدير النوافذ — يجمع الخمسة فوق واجهة الحاسوب، والإنسان
والآلة يعملان جنبًا إلى جنب بلا تخبط.

Stdlib only.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..events import EventBus
from .arbitration import InputArbitrator
from .monitors import MonitorLayout
from .overlay import OverlayController, build_overlay
from .ownership import InputOwner, OwnershipPolicy
from .registry import WindowRegistry

logger = logging.getLogger("nexus.windows")


class WindowManager:
    """The §10 composer — one object, the whole human-parallelism story."""

    def __init__(
        self,
        computer: Any,
        *,
        bus: EventBus | None = None,
        ownership: OwnershipPolicy | None = None,
        overlay: OverlayController | None = None,
        on_pause: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
    ) -> None:
        self._computer = computer
        self.registry = WindowRegistry(bus=bus)
        self.ownership = ownership or OwnershipPolicy()
        self.arbitrator = InputArbitrator(self.registry)
        self.monitors = MonitorLayout(computer)
        self.overlay = overlay or build_overlay(
            on_pause=on_pause, on_resume=on_resume
        )

    # ------------------------------------------------------------- sync

    def sync(self) -> dict[str, Any]:
        """Reconcile the registry with the live desktop (§10.1).

        Routes ``windows.list_windows`` (rows now carry pid · process
        · rect · minimized), ingests them, then resolves ownership
        for every record — one call, the whole §10.1/§10.2 state.
        """
        outcome = self._computer.windows("list_windows", limit=200)
        rows = (
            list(getattr(outcome, "artifacts", {}).get("windows", []))
            if getattr(outcome, "artifacts", None)
            else []
        )
        report = self.registry.ingest(rows)
        for record in self.registry.records():
            owner = self.ownership.resolve(record)
            if record.input_owner != owner:
                self.registry.update(record.window_id, input_owner=owner)
        return {
            "ingest": report.to_dict(),
            "ok": bool(outcome.ok),
            "error": getattr(outcome, "error", ""),
        }

    # ---------------------------------------------------------- claims

    def claim(
        self,
        window_id: str,
        *,
        owner: str = InputOwner.NEXUS,
        task_id: str = "",
        workspace: str = "",
        agent: str = "",
    ) -> dict[str, Any]:
        """Stake a window (the explicit §10.2 path)."""
        self.ownership.assign(window_id, owner)
        changes: dict[str, Any] = {"input_owner": owner}
        if task_id:
            changes["task_id"] = task_id
        if workspace:
            changes["workspace"] = workspace
        if agent:
            changes["agent"] = agent
        record = self.registry.update(window_id, **changes)
        return record.to_dict()

    def release(self, window_id: str) -> bool:
        """Drop an explicit claim (patterns/default take over again)."""
        released = self.ownership.release(window_id)
        record = self.registry.get(window_id)
        if record is not None:
            self.registry.update(
                window_id, input_owner=self.ownership.resolve(record),
                task_id="", workspace="", agent="",
            )
        return released

    # -------------------------------------------------------- overlay

    def begin(self, label: str = "") -> str:
        """Computer Use starts → the §10.5 overlay shows WORKING."""
        return self.overlay.begin(label)

    def pause(self) -> str:
        return self.overlay.pause()

    def resume(self) -> str:
        return self.overlay.resume()

    def end(self) -> str:
        return self.overlay.end()

    # ----------------------------------------------------------- hook

    def hook(self):
        """The §10.3 veto handler — register on ``pre_tool_call``."""
        return self.arbitrator.as_hook()

    # -------------------------------------------------------- snapshot

    def snapshot(self) -> dict[str, Any]:
        """The full §10 state: windows · ownership · monitors · overlay."""
        return {
            "phase": 9,
            "windows": self.registry.snapshot(),
            "ownership": self.ownership.summary(),
            "monitors": self.monitors.summary(),
            "overlay": self.overlay.snapshot(),
        }

    def shutdown(self) -> None:
        """Dismiss the overlay — idempotent, never raises."""
        try:
            self.overlay.shutdown()
        except Exception:  # noqa: BLE001 — teardown must never fail a shutdown
            logger.exception("overlay shutdown error — logged, shutdown continues")


def build_window_manager(
    computer: Any,
    *,
    bus: EventBus | None = None,
    ownership: OwnershipPolicy | None = None,
    on_pause: Callable[[], None] | None = None,
    on_resume: Callable[[], None] | None = None,
) -> WindowManager:
    """Compose the §10 manager over a live §9.1 Computer Runtime."""
    return WindowManager(
        computer,
        bus=bus,
        ownership=ownership,
        on_pause=on_pause,
        on_resume=on_resume,
    )


__all__ = [
    "WindowManager",
    "build_window_manager",
]
