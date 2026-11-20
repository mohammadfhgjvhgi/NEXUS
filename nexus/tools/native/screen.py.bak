"""Native tool: ``screen`` (Final Build Plan §8.3).

Three operations — ``size`` · ``screenshot`` · ``region`` — via GDI
(``user32`` + ``gdi32``) through :mod:`ctypes` on Windows; honest
unavailability elsewhere. The screenshot is a **real PNG** encoded
with stdlib ``zlib`` + ``struct`` (an IHDR/IDAT/IEND writer, filter
0) — no PIL, no external imaging dependency.

Phase 9 (Plan §10.4) adds the read-only ``monitors`` operation —
``EnumDisplayMonitors`` + ``GetMonitorInfoW`` (``MONITORINFOEXW``):
the monitor list with resolution, position, work area and the
primary flag. Risk stays 1 (pure enumeration, no mutation).

``screenshot`` writes to the ``path`` argument (scope-checked by the
§8.2 Scope stage — a screenshot is evidence and lands where the task
can keep it) and verifies itself via the ``path_size`` artifact.

The platform's own remote surface mirrors this family
(``cu_get_screen_size`` / ``cu_screenshot``, dl 1): NEXUS rates the
screen tools risk 1.

الشاشة — أبعاد ولقطة PNG حقيقية بترميز zlib قياسي، والمسار
خاضع للنطاق، والحجم برهان التحقق.

Stdlib only.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import struct
import sys
import zlib
from collections.abc import Mapping
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
    optional_str,
    output_schema,
    require_int,
    require_operation,
)

_OPERATIONS: tuple[str, ...] = ("size", "screenshot", "region", "monitors")

# GDI constants
_BI_RGB = 0
_DIB_RGB_COLORS = 0
_SRCCOPY = 0x00CC0020


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(width: int, height: int, bgra: bytes) -> bytes:
    """Encode 32-bit BGRA rows as a filter-0 RGB PNG (stdlib only)."""
    rgb = bytearray(width * height * 3)
    for source, target in zip(
        range(0, len(bgra), 4), range(0, len(rgb), 3), strict=False
    ):
        rgb[target] = bgra[source + 2]
        rgb[target + 1] = bgra[source + 1]
        rgb[target + 2] = bgra[source]
    stride = width * 3
    raw = bytearray()
    for row in range(height):
        raw.append(0)  # filter: None
        raw += rgb[row * stride : (row + 1) * stride]
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _png_chunk(b"IEND", b"")
    )


def _user32():
    if sys.platform != "win32":
        return None
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _monitor_rows() -> list[dict[str, Any]]:
    """§10.4 — EnumDisplayMonitors + GetMonitorInfoW (pure ctypes)."""
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    wintypes_ = wintypes

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes_.DWORD),
            ("rcMonitor", wintypes_.RECT),
            ("rcWork", wintypes_.RECT),
            ("dwFlags", wintypes_.DWORD),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    rows: list[dict[str, Any]] = []
    callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

    @callback_type(
        wintypes_.BOOL, wintypes_.HMONITOR, wintypes_.HDC,
        ctypes.POINTER(wintypes_.RECT), wintypes_.LPARAM,
    )
    def on_monitor(hmonitor: int, _hdc: int, _rect: Any, _data: int) -> bool:
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitor = info.rcMonitor
            work = info.rcWork
            rows.append(
                {
                    "handle": int(hmonitor),
                    "device": info.szDevice,
                    "rect": [
                        int(monitor.left), int(monitor.top),
                        int(monitor.right), int(monitor.bottom),
                    ],
                    "work": [
                        int(work.left), int(work.top),
                        int(work.right), int(work.bottom),
                    ],
                    "primary": bool(info.dwFlags & 1),  # MONITORINFOF_PRIMARY
                }
            )
        return True

    user32.EnumDisplayMonitors(None, None, on_monitor, 0)
    return rows


class ScreenTool(NativeTool):
    """§8.3 ``screen`` — GDI capture + stdlib PNG, risk 1."""

    name = "screen"

    def __init__(self, *, workspace_root: Any = None) -> None:
        self._root = workspace_root

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:screen",
            name=self.name,
            description=(
                "Screen capability (GDI/ctypes on Windows): size, "
                "screenshot(path), region(x, y, w, h, path). PNG output."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "path": {"type": "string", "description": "output PNG path"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "w": {"type": "integer"},
                    "h": {"type": "integer"},
                },
                required=("op",),
            ),
            output_schema=output_schema("screen record / PNG artifact / monitor rows"),
            permissions=("screen.read",),
            scope_requirements=ScopeRequirements(
                path_arguments=("path",),
                mutating_operations=(),  # writing a file is the tool's effect
                dimensions=("display",),
            ),
            risk=1,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        if operation == "size":
            return VerificationSpec(V.JSON_FIELD, "size")
        if operation == "monitors":
            return VerificationSpec(V.JSON_FIELD, "count")
        return VerificationSpec(V.PATH_SIZE)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        from pathlib import Path

        operation = require_operation(arguments, _OPERATIONS)
        if sys.platform != "win32":
            raise ToolArgError(
                "op",
                f"screen tool requires win32 GDI (this runtime is {sys.platform})",
            )
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        gdi32 = ctypes.windll.gdi32  # type: ignore[attr-defined]
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        if operation == "size":
            record = {"width": width, "height": height}
            return ToolCallResult(output=str(record), artifacts={"size": record})
        if operation == "monitors":
            rows = _monitor_rows()
            lines = []
            for index, row in enumerate(rows):
                left, top, right, bottom = row["rect"]
                lines.append(
                    f"mon-{index}  {row['device']}  "
                    f"{right - left}x{bottom - top} @ ({left},{top})"
                    + ("  primary" if row["primary"] else "")
                )
            return ToolCallResult(
                output="\n".join(lines) if lines else "(no monitors)",
                artifacts={"monitors": rows, "count": len(rows)},
            )
        region = (
            require_int(arguments, "x", default=0, low=0, high=1 << 15),
            require_int(arguments, "y", default=0, low=0, high=1 << 15),
            require_int(
                arguments, "w", default=width, low=1, high=1 << 15
            ),
            require_int(
                arguments, "h", default=height, low=1, high=1 << 15
            ),
        )
        raw_path = optional_str(arguments, "path") or "screenshot.png"
        path = Path(raw_path)
        if not path.is_absolute() and self._root is not None:
            path = self._root / path
        png = self._capture(user32, gdi32, region)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        return ToolCallResult(
            output=(
                f"screenshot {region[2]}x{region[3]} → {path} "
                f"({len(png)} bytes PNG)"
            ),
            artifacts={
                "path": str(path),
                "bytes": len(png),
                "size": {"width": region[2], "height": region[3]},
            },
        )

    def _capture(self, user32: Any, gdi32: Any, region: tuple[int, int, int, int]) -> bytes:
        x, y, width, height = region
        hdc_screen = user32.GetDC(None)
        hdc_memory = gdi32.CreateCompatibleDC(hdc_screen)
        bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        gdi32.SelectObject(hdc_memory, bitmap)
        gdi32.BitBlt(
            hdc_memory, 0, 0, width, height, hdc_screen, x, y, _SRCCOPY
        )

        class _BitmapInfoHeader(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        header = _BitmapInfoHeader()
        header.biSize = ctypes.sizeof(_BitmapInfoHeader)
        header.biWidth = width
        header.biHeight = -height  # top-down rows
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = _BI_RGB
        buffer_size = width * height * 4
        buffer = ctypes.create_string_buffer(buffer_size)
        drawn = gdi32.GetDIBits(
            hdc_memory, bitmap, 0, height, buffer, ctypes.byref(header), _DIB_RGB_COLORS
        )
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(hdc_memory)
        user32.ReleaseDC(None, hdc_screen)
        if not drawn:
            raise ToolArgError("op", "GetDIBits failed — capture unavailable")
        return encode_png(width, height, buffer.raw[:buffer_size])

    def capabilities(self) -> CapabilityReport:
        if sys.platform == "win32":
            return CapabilityReport(
                available=True, reason="GDI capture + stdlib PNG encoder"
            )
        return CapabilityReport(
            available=False,
            reason=f"win32 GDI required (this runtime is {sys.platform})",
        )
