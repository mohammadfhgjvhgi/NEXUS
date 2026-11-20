"""Native tool: ``windows`` (Final Build Plan §8.3).

Window management over ``user32.dll`` via :mod:`ctypes` — no pywin32
needed: ``list_windows`` (EnumWindows + visible titles, now with
pid · process · rect · minimized — the §10.1 registry feeds on
these rows), ``active_window`` (GetForegroundWindow), ``focus``
(SetForegroundWindow), ``minimize``/``maximize``/``restore``
(ShowWindow), ``close`` (PostMessage WM_CLOSE — the polite close).

Phase 9 (Plan §10.4) adds ``geometry`` (GetWindowRect +
MonitorFromWindow + IsIconic — the read-only placement facts) and
``move`` (SetWindowPos with SWP_NOZORDER — the window-placement
effect, routed like every other real effect). Risk stays 2.

On non-Windows platforms the capability probe reports unavailable
honestly and every call fails with the reason — the registry keeps
the tool (the §8.2 discovery reports it) instead of hiding it.

The platform's own remote surface mirrors this family
(``cu_list_windows`` dl 1) — NEXUS rates window control risk 2.

إدارة النوافذ عبر user32 بلا pywin32، وتوافر صادق لكل منصة.

Stdlib only.
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Mapping
from ctypes import wintypes
from typing import Any

from ..models import (
    CapabilityReport,
    ScopeRequirements,
    ToolCallResult,
    ToolDefinition,
    VerificationSpec,
)
from ..models import (
    VerificationStrategy as V,
)
from .base import (
    NativeTool,
    ToolArgError,
    object_schema,
    output_schema,
    require_int,
    require_operation,
)

_OPERATIONS: tuple[str, ...] = (
    "list_windows",
    "active_window",
    "focus",
    "minimize",
    "maximize",
    "restore",
    "close",
    "geometry",
    "move",
)

_SW = {"minimize": 6, "maximize": 3, "restore": 9}
_WM_CLOSE = 0x0010
_MONITOR_DEFAULTTONEAREST = 2
_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _user32():
    if sys.platform != "win32":
        return None
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _window_rows(limit: int) -> list[dict[str, Any]]:
    user32 = _require_user32()
    rows: list[dict[str, Any]] = []
    callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

    @callback_type(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def on_window(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(
                    hwnd, ctypes.byref(pid)
                )
                rows.append(
                    {
                        "hwnd": hwnd,
                        "title": buffer.value,
                        "pid": int(pid.value),
                        "process": _process_name(pid.value),
                        "rect": [
                            int(rect.left), int(rect.top),
                            int(rect.right), int(rect.bottom),
                        ],
                        "minimized": bool(user32.IsIconic(hwnd)),
                    }
                )
        return len(rows) < limit

    user32.EnumWindows(on_window, 0)
    return rows


def _process_name(pid: int) -> str:
    """Owning process exe (QueryFullProcessImageNameW, pure ctypes)."""
    if not pid:
        return ""
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _geometry_record(user32: Any, hwnd: int) -> dict[str, Any]:
    """§10.4 facts for one window: rect · monitor · minimized."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    monitor = user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
    device = ""
    if monitor:
        info = _monitorinfo_struct()
        info.cbSize = ctypes.sizeof(info.__class__)  # type: ignore[attr-defined]
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            device = info.szDevice
    return {
        "hwnd": hwnd,
        "rect": [
            int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        ],
        "position": [int(rect.left), int(rect.top)],
        "size": [
            int(rect.right - rect.left), int(rect.bottom - rect.top)
        ],
        "monitor": device,
        "minimized": bool(user32.IsIconic(hwnd)),
    }


def _monitorinfo_struct() -> Any:
    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    return _MONITORINFOEXW()


def _require_user32() -> Any:
    user32 = _user32()
    if user32 is None:
        raise ToolArgError(
            "op",
            "windows tool requires the win32 platform "
            f"(this runtime is {sys.platform})",
        )
    return user32


class WindowsTool(NativeTool):
    """§8.3 ``windows`` — user32 window control, risk 2."""

    name = "windows"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:windows",
            name=self.name,
            description=(
                "Window capability (user32/ctypes): list_windows, "
                "active_window, focus(hwnd), minimize/maximize/restore(hwnd), "
                "close(hwnd), geometry(hwnd), move(hwnd, x, y, w, h)."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "hwnd": {"type": "integer", "description": "window handle"},
                    "limit": {"type": "integer", "description": "list bound"},
                    "x": {"type": "integer", "description": "move target left"},
                    "y": {"type": "integer", "description": "move target top"},
                    "w": {"type": "integer", "description": "target width (optional)"},
                    "h": {"type": "integer", "description": "target height (optional)"},
                },
                required=("op",),
            ),
            output_schema=output_schema("window rows / record / control result"),
            permissions=("windows.control",),
            scope_requirements=ScopeRequirements(
                path_arguments=(),
                mutating_operations=(
                    "focus", "minimize", "maximize", "restore", "close", "move"
                ),
                dimensions=("display",),
            ),
            risk=2,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        if operation == "list_windows":
            return VerificationSpec(V.JSON_FIELD, "windows")
        if operation == "active_window":
            return VerificationSpec(V.JSON_FIELD, "window")
        if operation == "geometry":
            return VerificationSpec(V.JSON_FIELD, "geometry")
        return VerificationSpec(V.EXIT_ZERO)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        if operation == "list_windows":
            limit = require_int(arguments, "limit", default=50, low=1, high=1000)
            rows = _window_rows(limit)
            lines = [
                f"{row['hwnd']:>10}  {row['process'] or '?':<24}  {row['title']}"
                for row in rows
            ]
            return ToolCallResult(
                output="\n".join(lines) if lines else "(no visible windows)",
                artifacts={"windows": rows, "count": len(rows)},
            )
        user32 = _require_user32()
        if operation == "active_window":
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            record = {"hwnd": hwnd, "title": buffer.value}
            return ToolCallResult(output=str(record), artifacts={"window": record})
        hwnd = require_int(arguments, "hwnd", default=0, low=1, high=1 << 31)
        if operation == "geometry":
            record = _geometry_record(user32, hwnd)
            return ToolCallResult(
                output=str(record), artifacts={"geometry": record}
            )
        if operation == "move":
            x = require_int(arguments, "x", default=0, low=-32768, high=32767)
            y = require_int(arguments, "y", default=0, low=-32768, high=32767)
            raw_w, raw_h = arguments.get("w"), arguments.get("h")
            flags = _SWP_NOZORDER | _SWP_NOACTIVATE
            width = height = 0
            if isinstance(raw_w, int) and isinstance(raw_h, int):
                if not (0 < raw_w <= 32768 and 0 < raw_h <= 32768):
                    raise ToolArgError(
                        "w", "move sizes must be positive and sane (w and h together)"
                    )
                width, height = raw_w, raw_h
            else:
                flags |= _SWP_NOSIZE  # keep the current size
            ok = bool(
                user32.SetWindowPos(
                    hwnd, 0, x, y, width, height, flags
                )
            )
            return self._control(operation, hwnd, ok)
        if operation == "focus":
            ok = bool(user32.SetForegroundWindow(hwnd))
            return self._control(operation, hwnd, ok)
        if operation == "close":
            ok = bool(user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0))
            return self._control(operation, hwnd, ok)
        # minimize / maximize / restore
        ok = bool(user32.ShowWindow(hwnd, _SW[operation]))
        return self._control(operation, hwnd, ok)

    def _control(
        self, operation: str, hwnd: int, ok: bool
    ) -> ToolCallResult:
        return ToolCallResult(
            output=(
                f"{operation} → hwnd {hwnd}: {'ok' if ok else 'failed'}"
            ),
            artifacts={"op": operation, "hwnd": hwnd, "exit_code": 0 if ok else 1},
        )

    def capabilities(self) -> CapabilityReport:
        if sys.platform == "win32":
            return CapabilityReport(available=True, reason="user32 via ctypes")
        return CapabilityReport(
            available=False,
            reason=f"win32-only (this runtime is {sys.platform})",
        )
