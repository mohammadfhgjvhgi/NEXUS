"""Window Registry (Final Build Plan §10.1 — Spec §60).

Every window NEXUS manages gets a record with the nine verbatim
fields:

===================  ==================================================
``window_id``        stable registry key (``win-<hwnd>`` on Windows)
``application``      owning process name (``chrome.exe`` …)
``task_id``          the task that claimed the window ("" = none)
``workspace``        the workspace the claim belongs to
``agent``            the agent the claim belongs to
``position``         (x, y) — top-left, virtual-desktop coordinates
``size``             (width, height)
``visibility``       visible · minimized · hidden
``input_owner``      USER · NEXUS · SHARED (Spec §62 — input ownership)
===================  ==================================================

The registry is *stateful bookkeeping, not a second aperture*: real
effects still flow through the §8.2 router. :meth:`ingest` reconciles
live window rows (the §9.1 ``windows`` domain artifacts) into records
and — for the first time in the platform — actually publishes the two
canonical §2.2 events ``window.opened`` / ``window.closed`` that have
sat in the 28-event registry since Phase 1. Ownership and task
bindings are *NEXUS decisions* and survive geometry refreshes; the
machine may move a window, only NEXUS decides who owns its input.

سجلّ النوافذ — الحقول التسعة حرفيًا، والمصالحة تنشر حدثي
window.opened / window.closed فعليًا لأول مرة منذ المرحلة 1.

Stdlib only.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from ..events import EventBus, EventName

logger = logging.getLogger("nexus.windows")

#: The §10.1 visibility vocabulary (honest: only what Win32 tells us).
VISIBILITIES: tuple[str, ...] = ("visible", "minimized", "hidden")

#: The §62 input-owner vocabulary is defined in ownership.py; the
#: registry stores it as a plain string so the record stays decoupled
#: from the policy module (bookkeeping vs. decisions).
INPUT_OWNERS: tuple[str, ...] = ("USER", "NEXUS", "SHARED")


def window_id_for(hwnd: int) -> str:
    """The stable registry key for a Win32 window handle."""
    return f"win-{int(hwnd)}"


def _as_point(value: Any) -> tuple[int, int]:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return int(value[0]), int(value[1])
    return (0, 0)


@dataclass(frozen=True, slots=True)
class WindowRecord:
    """One managed window — the §10.1 nine fields, verbatim order."""

    window_id: str
    application: str = ""
    task_id: str = ""
    workspace: str = ""
    agent: str = ""
    position: tuple[int, int] = (0, 0)
    size: tuple[int, int] = (0, 0)
    visibility: str = "visible"
    input_owner: str = "USER"
    #: platform bridge fields — *not* part of the §10.1 nine: the raw
    #: handle (0 for synthetic/test records) and the live title text
    #: (needed by §10.2 title rules; the machine may change it).
    hwnd: int = 0
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "application": self.application,
            "task_id": self.task_id,
            "workspace": self.workspace,
            "agent": self.agent,
            "position": list(self.position),
            "size": list(self.size),
            "visibility": self.visibility,
            "input_owner": self.input_owner,
            "hwnd": self.hwnd,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class IngestReport:
    """What one :meth:`WindowRegistry.ingest` changed — audit-ready."""

    opened: tuple[str, ...] = ()
    closed: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "opened": list(self.opened),
            "closed": list(self.closed),
            "updated": list(self.updated),
            "total": self.total,
        }


def _visibility_of(row: Mapping[str, Any]) -> str:
    """Honest visibility from a live row: minimized beats visible."""
    if bool(row.get("minimized", False)):
        return "minimized"
    if bool(row.get("visible", True)):
        return "visible"
    return "hidden"


class WindowRegistry:
    """The §10.1 registry — reconcile, query, and publish.

    * :meth:`ingest` — diff live rows into records; new windows open,
      vanished windows close, survivors get geometry refreshes; task
      bindings and input ownership are preserved (NEXUS decisions);
    * :meth:`get` / :meth:`find` — by window_id or raw handle;
    * :meth:`update` — the single write path for NEXUS decisions
      (ownership, task claim) so every mutation is one audit seam.
    """

    def __init__(self, *, bus: EventBus | None = None) -> None:
        self._records: dict[str, WindowRecord] = {}
        self._bus = bus

    # ------------------------------------------------------------ ingest

    def ingest(self, rows: Iterable[Mapping[str, Any]]) -> IngestReport:
        """Reconcile live window rows into the registry.

        Each row is a ``windows`` domain artifact: ``hwnd`` · ``title``
        · optional ``process``/``application`` · optional ``rect``
        ``(x, y, w, h)`` · optional ``minimized``/``visible`` flags.
        Rows without an ``hwnd`` are ignored honestly (the registry
        keys on the real handle).
        """
        opened: list[str] = []
        updated: list[str] = []
        seen: set[str] = set()
        for row in rows:
            raw_hwnd = row.get("hwnd")
            if isinstance(raw_hwnd, bool) or not isinstance(raw_hwnd, int) or raw_hwnd < 1:
                continue
            hwnd = raw_hwnd
            window_id = window_id_for(hwnd)
            seen.add(window_id)
            application = str(row.get("application") or row.get("process") or "")
            title = str(row.get("title") or "")
            rect = row.get("rect")
            if isinstance(rect, (tuple, list)) and len(rect) == 4:
                # Win32 GetWindowRect order: (left, top, right, bottom)
                # — exactly what the §8.3 windows tool emits.
                left, top, right, bottom = (int(v) for v in rect)
                position = (left, top)
                size = (max(0, right - left), max(0, bottom - top))
            else:
                position, size = (0, 0), (0, 0)
            visibility = _visibility_of(row)
            current = self._records.get(window_id)
            if current is None:
                record = WindowRecord(
                    window_id=window_id,
                    application=application,
                    title=title,
                    position=position,
                    size=size,
                    visibility=visibility,
                    hwnd=hwnd,
                )
                self._records[window_id] = record
                opened.append(window_id)
            elif (
                current.position != position
                or current.size != size
                or current.visibility != visibility
                or current.application != application
                or current.title != title
            ):
                self._records[window_id] = replace(
                    current,
                    application=application or current.application,
                    title=title or current.title,
                    position=position,
                    size=size,
                    visibility=visibility,
                )
                updated.append(window_id)
        closed: list[str] = []
        for window_id in list(self._records):
            if window_id not in seen:
                closed.append(window_id)
                del self._records[window_id]
        report = IngestReport(
            opened=tuple(opened),
            closed=tuple(closed),
            updated=tuple(updated),
            total=len(self._records),
        )
        self._publish(report)
        logger.debug("ingest: %s", report.to_dict())
        return report

    def _publish(self, report: IngestReport) -> None:
        """The first real publisher of the two canonical §2.2 events."""
        if self._bus is None:
            return
        for window_id in report.opened:
            record = self._records.get(window_id)
            payload = record.to_dict() if record else {"window_id": window_id}
            self._bus.publish(
                EventName.WINDOW_OPENED,
                payload=payload,
                source="nexus.windows.registry",
            )
        for window_id in report.closed:
            self._bus.publish(
                EventName.WINDOW_CLOSED,
                payload={"window_id": window_id},
                source="nexus.windows.registry",
            )

    # ------------------------------------------------------------- query

    def get(self, window_id: str) -> WindowRecord | None:
        return self._records.get(window_id)

    def find(self, hwnd: int) -> WindowRecord | None:
        return self._records.get(window_id_for(hwnd))

    def by_owner(self, owner: str) -> tuple[WindowRecord, ...]:
        return tuple(r for r in self._records.values() if r.input_owner == owner)

    def records(self) -> tuple[WindowRecord, ...]:
        return tuple(self._records.values())

    def count(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------- write

    def update(self, window_id: str, **changes: Any) -> WindowRecord:
        """One audit seam for NEXUS decisions on a record.

        Allowed keys: ``application``, ``task_id``, ``workspace``,
        ``agent``, ``input_owner`` — geometry/visibility belong to the
        machine (refresh via :meth:`ingest`), so they are refused.
        """
        current = self._records.get(window_id)
        if current is None:
            raise KeyError(f"unknown window_id {window_id!r}")
        if not changes:
            return current
        geometry_keys = {"position", "size", "visibility", "window_id", "hwnd"}
        illegal = geometry_keys.intersection(changes)
        if illegal:
            raise ValueError(
                f"machine-owned fields {sorted(illegal)} change only via ingest()"
            )
        if "input_owner" in changes and changes["input_owner"] not in INPUT_OWNERS:
            raise ValueError(
                f"input_owner must be one of {INPUT_OWNERS}, "
                f"got {changes['input_owner']!r}"
            )
        updated = replace(current, **changes)
        self._records[window_id] = updated
        return updated

    # -------------------------------------------------------- snapshot

    def snapshot(self) -> dict[str, Any]:
        return {
            "count": len(self._records),
            "windows": [record.to_dict() for record in self._records.values()],
        }
