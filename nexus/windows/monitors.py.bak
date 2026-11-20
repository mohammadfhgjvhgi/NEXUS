"""Multiple Monitors (Final Build Plan §10.4 — Spec §61/§63 context).

The monitor topology NEXUS must know — verbatim:

===================  ==================================================
``monitor list``     every display in the virtual desktop
``resolution``       (width, height) per monitor
``position``         (x, y) top-left in virtual-desktop coordinates
``window placement`` which monitor a window is on · move to one
===================  ==================================================

The live enumeration lives in the §8.3 ``screen`` tool (new op
``monitors`` — ``EnumDisplayMonitors`` + ``GetMonitorInfoW`` via
ctypes, risk 1 read-only, honest off win32). This module is the
*policy* layer over the §9.1 Computer API: :meth:`MonitorLayout.snapshot`
routes through ``screens.monitors``, :meth:`monitor_for_window` reads
the extended ``windows.geometry``, and :meth:`place` computes a
placement rect (pure math, testable anywhere) then routes the move
through ``windows.move`` — **every real effect behind the §8.2 router**,
the MonitorLayout itself never touches user32.

طوبولوجيا الشاشات — قائمة وأبعاد ومواضع وموضعة النوافذ، وكل
تأثير حقيقي خلف الموجّه نفسه.

Stdlib only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("nexus.windows")

#: MONITORINFOF_PRIMARY — the flag GetMonitorInfoW reports.
_MONITOR_PRIMARY = 1


@dataclass(frozen=True, slots=True)
class MonitorRecord:
    """One display in the virtual desktop (§10.4 fields, verbatim)."""

    monitor_id: str  # "mon-0", "mon-1", … (enumeration order)
    resolution: tuple[int, int]  # (width, height)
    position: tuple[int, int]  # (x, y) — virtual-desktop coordinates
    work_area: tuple[int, int, int, int]  # (left, top, right, bottom)
    primary: bool
    device: str = ""  # e.g. r"\\.\DISPLAY1" (win32 device name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitor_id": self.monitor_id,
            "resolution": list(self.resolution),
            "position": list(self.position),
            "work_area": list(self.work_area),
            "primary": self.primary,
            "device": self.device,
        }

    @property
    def width(self) -> int:
        return self.resolution[0]

    @property
    def height(self) -> int:
        return self.resolution[1]


def _record_from_row(index: int, row: dict[str, Any]) -> MonitorRecord:
    rect = row.get("rect") or row.get("work") or (0, 0, 0, 0)
    left, top, right, bottom = (int(value) for value in rect[:4])
    work = row.get("work", rect)
    work_left, work_top, work_right, work_bottom = (int(v) for v in tuple(work)[:4])
    return MonitorRecord(
        monitor_id=f"mon-{index}",
        resolution=(right - left, bottom - top),
        position=(left, top),
        work_area=(work_left, work_top, work_right, work_bottom),
        primary=bool(row.get("primary", False)),
        device=str(row.get("device", "")),
    )


class MonitorLayout:
    """The §10.4 policy layer over the Computer API domains."""

    def __init__(self, computer: Any) -> None:
        self._computer = computer

    # ------------------------------------------------------------ probes

    def snapshot(self) -> tuple[MonitorRecord, ...]:
        """The monitor list — routed through ``screens.monitors``."""
        outcome = self._computer.screens("monitors")
        rows = (
            outcome.artifacts.get("monitors", [])
            if getattr(outcome, "artifacts", None)
            else []
        )
        if not outcome.ok:
            logger.warning("monitors probe failed: %s", outcome.error)
            return ()
        return tuple(_record_from_row(i, row) for i, row in enumerate(rows))

    def monitor_for_window(self, hwnd: int) -> MonitorRecord | None:
        """Which monitor a window is on — via ``windows.geometry``."""
        outcome = self._computer.windows("geometry", hwnd=hwnd)
        if not outcome.ok:
            logger.warning("geometry probe failed for %s: %s", hwnd, outcome.error)
            return None
        artifacts = getattr(outcome, "artifacts", None) or {}
        geometry = artifacts.get("geometry", {})
        device = str(geometry.get("monitor", ""))
        if not device:
            return None
        for record in self.snapshot():
            if record.device == device:
                return record
        return None

    # --------------------------------------------------------- placement

    @staticmethod
    def placement_rect(
        monitor: MonitorRecord,
        size: tuple[int, int],
        *,
        anchor: str = "center",
        margin: int = 32,
    ) -> tuple[int, int, int, int]:
        """Pure placement math — (x, y, w, h) inside the work area.

        ``anchor``: ``center`` · ``top-left`` · ``bottom-right``. The
        rect is clamped to the monitor's work area (never the
        taskbar). No Win32 call here — CI tests this everywhere.
        """
        if anchor not in ("center", "top-left", "bottom-right"):
            raise ValueError(f"anchor must be center|top-left|bottom-right, got {anchor!r}")
        if margin < 0:
            raise ValueError("margin must be >= 0")
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        left, top, right, bottom = monitor.work_area
        available_w = max(1, right - left - 2 * margin)
        available_h = max(1, bottom - top - 2 * margin)
        width = min(width, available_w)
        height = min(height, available_h)
        if anchor == "center":
            x = left + (right - left - width) // 2
            y = top + (bottom - top - height) // 2
        elif anchor == "top-left":
            x, y = left + margin, top + margin
        else:
            x = right - margin - width
            y = bottom - margin - height
        return (x, y, width, height)

    def place(
        self,
        hwnd: int,
        monitor_id: str,
        *,
        anchor: str = "center",
        margin: int = 32,
        size: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        """Move a window onto a monitor (§10.4 window placement).

        Keeps the window's current size unless ``size`` is given;
        the computed rect routes through ``windows.move`` — the only
        place a real effect happens (the §8.2 pipeline runs).
        """
        monitors = {record.monitor_id: record for record in self.snapshot()}
        target = monitors.get(monitor_id)
        if target is None:
            raise ValueError(
                f"unknown monitor_id {monitor_id!r} (have {sorted(monitors)})"
            )
        if size is None:
            geometry = self._current_geometry(hwnd)
            size = (geometry[2], geometry[3])
        x, y, width, height = self.placement_rect(
            target, size, anchor=anchor, margin=margin
        )
        outcome = self._computer.windows(
            "move", hwnd=hwnd, x=x, y=y, w=width, h=height
        )
        return {
            "ok": bool(outcome.ok),
            "monitor": monitor_id,
            "rect": [x, y, width, height],
            "error": getattr(outcome, "error", ""),
        }

    def _current_geometry(self, hwnd: int) -> tuple[int, int, int, int]:
        """(left, top, width, height) — computed, never raw LTRB."""
        outcome = self._computer.windows("geometry", hwnd=hwnd)
        artifacts = getattr(outcome, "artifacts", None) or {}
        rect = (artifacts.get("geometry", {}) or {}).get("rect", (0, 0, 640, 480))
        left, top, right, bottom = (int(v) for v in tuple(rect)[:4])
        return (left, top, max(1, right - left), max(1, bottom - top))

    def summary(self) -> dict[str, Any]:
        monitors = self.snapshot()
        return {
            "count": len(monitors),
            "monitors": [record.to_dict() for record in monitors],
        }


__all__ = [
    "MonitorLayout",
    "MonitorRecord",
]
