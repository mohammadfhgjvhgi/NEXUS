"""Screen Capture layer (Final Build Plan §12.1, verbatim).

Three capture modes:

* **full screen** — the primary monitor's virtual desktop via GDI
  ``BitBlt`` (the Phase-7 ``screen`` tool path, generalized).
* **window** — one window by ``hwnd``: ``PrintWindow`` with
  ``PW_RENDERFULLCONTENT`` (captures DirectComposition content the
  classic BitBlt misses — Chrome/Edge/Electron), with an honest
  BitBlt fallback at the window's bounds.
* **region** — one ``ScreenRegion`` rectangle of the screen.

The transport is a single injectable backend (``Win32Gdi``), so the
layer's math — region clamping, window bounds resolution, capture
target computation — is CI-testable anywhere; the GDI itself needs
win32 and reports that honestly (Spec §9: unavailable → reported,
never faked).

Window bounds use the DWM **extended frame bounds** when available
(``DwmGetWindowAttribute`` — the shadow-inclusive ``GetWindowRect``
lies about where pixels actually are) with ``GetWindowRect`` as the
fallback. The PNG encoding is the Phase-7 stdlib encoder
(:func:`nexus.tools.native.screen.encode_png`) — one encoder, one
format, no imaging dependency.

طبقة الالتقاط — الشاشة كاملة أو نافذة أو منطقة، والرياضيات
صافية قابلة للاختبار، والغربلة صادقة خارج ويندوز.

Stdlib only.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import struct
import sys
from typing import Any, Protocol

from .models import CAPTURE_MODES, CaptureResult, ScreenRegion

#: PrintWindow flag: render full window content (DWM/DirectComposition).
PW_RENDERFULLCONTENT = 0x00000002

#: DwmGetWindowAttribute attribute: the actual window bounds.
DWMWA_EXTENDED_FRAME_BOUNDS = 9

_BI_RGB = 0
_DIB_RGB_COLORS = 0
_SRCCOPY = 0x00CC0020


class CaptureError(Exception):
    """A capture attempt failed — honest, with the mode that failed."""


# --------------------------------------------------------------- backend


class CaptureBackend(Protocol):
    """The GDI transport contract (injectable for tests)."""

    def screen_size(self) -> tuple[int, int]:
        """The primary virtual-desktop size (width, height)."""
        ...

    def grab_region(self, x: int, y: int, width: int, height: int) -> bytes:
        """BitBlt one screen rectangle → top-down 32-bit BGRA rows."""
        ...

    def grab_window(self, hwnd: int, width: int, height: int) -> bytes:
        """PrintWindow(PW_RENDERFULLCONTENT) → BGRA rows (BitBlt fallback
        decided inside the concrete backend)."""
        ...

    def window_bounds(self, hwnd: int) -> tuple[int, int, int, int]:
        """The window's real pixel bounds → (x, y, width, height)."""
        ...


class Win32Gdi:
    """The production backend — pure ctypes GDI/DWM, win32 only."""

    def screen_size(self) -> tuple[int, int]:
        user32 = _user32()
        return (
            int(user32.GetSystemMetrics(0)),
            int(user32.GetSystemMetrics(1)),
        )

    def grab_region(self, x: int, y: int, width: int, height: int) -> bytes:
        user32, gdi32 = _user32(), _gdi32()
        hdc_screen = user32.GetDC(None)
        try:
            hdc_memory = gdi32.CreateCompatibleDC(hdc_screen)
            bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
            gdi32.SelectObject(hdc_memory, bitmap)
            gdi32.BitBlt(
                hdc_memory, 0, 0, width, height, hdc_screen, x, y, _SRCCOPY
            )
            rows = _get_dibits(gdi32, hdc_memory, bitmap, width, height)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(hdc_memory)
        finally:
            user32.ReleaseDC(None, hdc_screen)
        return rows

    def grab_window(self, hwnd: int, width: int, height: int) -> bytes:
        user32, gdi32 = _user32(), _gdi32()
        # PrintWindow renders offscreen content (DWM) a BitBlt of the
        # screen rectangle cannot see — occluded windows included.
        hdc_window = user32.GetWindowDC(hwnd)
        if not hdc_window:
            raise CaptureError(f"GetWindowDC failed for hwnd {hwnd}")
        try:
            hdc_memory = gdi32.CreateCompatibleDC(hdc_window)
            bitmap = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
            gdi32.SelectObject(hdc_memory, bitmap)
            printed = user32.PrintWindow(hwnd, hdc_memory, PW_RENDERFULLCONTENT)
            if not printed:
                # honest fallback: copy the on-screen pixels at the
                # window bounds (the pre-DWM path)
                gdi32.BitBlt(
                    hdc_memory, 0, 0, width, height,
                    hdc_window, 0, 0, _SRCCOPY,
                )
            rows = _get_dibits(gdi32, hdc_memory, bitmap, width, height)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(hdc_memory)
        finally:
            user32.ReleaseDC(hwnd, hdc_window)
        return rows

    def window_bounds(self, hwnd: int) -> tuple[int, int, int, int]:
        user32 = _user32()
        rect = wintypes.RECT()
        # Prefer the DWM extended frame bounds — GetWindowRect includes
        # the invisible resize shadow on DWM windows.
        try:
            dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
            value = ctypes.pointer(rect)
            if dwm.DwmGetWindowAttribute(
                hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, value, ctypes.sizeof(rect)
            ) == 0 and rect.right > rect.left:
                return (
                    int(rect.left), int(rect.top),
                    int(rect.right - rect.left),
                    int(rect.bottom - rect.top),
                )
        except (AttributeError, OSError):
            pass  # pre-Vista or no DWM — the classic rect below
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise CaptureError(f"GetWindowRect failed for hwnd {hwnd}")
        return (
            int(rect.left), int(rect.top),
            int(rect.right - rect.left),
            int(rect.bottom - rect.top),
        )


def _user32() -> Any:
    if sys.platform != "win32":
        raise CaptureError(
            f"screen capture requires win32 GDI (this runtime is {sys.platform})"
        )
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _gdi32() -> Any:
    if sys.platform != "win32":
        raise CaptureError(
            f"screen capture requires win32 GDI (this runtime is {sys.platform})"
        )
    return ctypes.windll.gdi32  # type: ignore[attr-defined]


def _get_dibits(
    gdi32: Any, hdc: Any, bitmap: Any, width: int, height: int
) -> bytes:
    """Extract one bitmap as top-down 32-bit BGRA rows (stdlib)."""

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
    size = width * height * 4
    buffer = ctypes.create_string_buffer(size)
    drawn = gdi32.GetDIBits(
        hdc, bitmap, 0, height, buffer, ctypes.byref(header), _DIB_RGB_COLORS
    )
    if not drawn:
        raise CaptureError("GetDIBits failed — capture unavailable")
    return buffer.raw[:size]


def _encode(width: int, height: int, bgra: bytes) -> bytes:
    """The Phase-7 stdlib PNG encoder (one encoder, one format)."""
    from ..tools.native.screen import encode_png

    return encode_png(width, height, bgra)


# ------------------------------------------------------------- the layer


def capture_available(backend: CaptureBackend | None = None) -> tuple[bool, str]:
    """Honest probe — win32 GDI or an injected test backend."""
    if sys.platform != "win32" and backend is None:
        return False, f"win32 GDI required (this runtime is {sys.platform})"
    return True, "GDI capture + stdlib PNG encoder (full · window · region)"


def capture_full_screen(
    backend: CaptureBackend | None = None,
) -> CaptureResult:
    """§12.1 mode ``full`` — the whole primary virtual desktop."""
    gdi = backend if backend is not None else Win32Gdi()
    width, height = gdi.screen_size()
    if width < 1 or height < 1:
        raise CaptureError(f"screen size unavailable ({width}x{height})")
    region = ScreenRegion(0, 0, width, height)
    return _finish(
        "full", gdi.grab_region(0, 0, width, height), region, "screen"
    )


def capture_window(
    hwnd: int, backend: CaptureBackend | None = None
) -> CaptureResult:
    """§12.1 mode ``window`` — one window, occlusion-proof."""
    if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd < 1:
        raise CaptureError("window capture requires a positive hwnd")
    gdi = backend if backend is not None else Win32Gdi()
    x, y, width, height = gdi.window_bounds(hwnd)
    if width < 1 or height < 1:
        raise CaptureError(f"window {hwnd} has no visible bounds")
    rows = gdi.grab_window(hwnd, width, height)
    region = ScreenRegion(x, y, width, height)
    return _finish("window", rows, region, f"hwnd:{hwnd}")


def capture_region(
    region: ScreenRegion, backend: CaptureBackend | None = None
) -> CaptureResult:
    """§12.1 mode ``region`` — one clamped screen rectangle."""
    if region.width < 1 or region.height < 1:
        raise CaptureError("region must be at least 1x1")
    gdi = backend if backend is not None else Win32Gdi()
    screen_width, screen_height = gdi.screen_size()
    bounds = ScreenRegion(0, 0, screen_width, screen_height)
    clipped = region.clamp_to(bounds)
    if clipped.width < 1 or clipped.height < 1:
        raise CaptureError(
            f"region {region.to_dict()} lies outside the screen "
            f"({screen_width}x{screen_height})"
        )
    rows = gdi.grab_region(
        clipped.x, clipped.y, clipped.width, clipped.height
    )
    return _finish("region", rows, clipped, "screen")


def resolve_capture_mode(mode: str) -> str:
    """Validate one §12.1 mode name against the verbatim vocabulary."""
    if mode not in CAPTURE_MODES:
        raise CaptureError(
            f"capture mode must be one of {list(CAPTURE_MODES)}, got {mode!r}"
        )
    return mode


def png_dimensions(png: bytes) -> tuple[int, int]:
    """Read one PNG's (width, height) from its IHDR (pure stdlib)."""
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise CaptureError("not a PNG image")
    width, height = struct.unpack(">II", png[16:24])
    return int(width), int(height)


def _finish(
    mode: str, bgra: bytes, region: ScreenRegion, source: str
) -> CaptureResult:
    png = _encode(region.width, region.height, bgra)
    if len(png) < 1:
        raise CaptureError("PNG encoding produced no bytes")
    return CaptureResult(
        mode=mode,
        png=png,
        width=region.width,
        height=region.height,
        source=source,
        region=region,
    )


__all__ = [
    "CaptureBackend",
    "CaptureError",
    "DWMWA_EXTENDED_FRAME_BOUNDS",
    "PW_RENDERFULLCONTENT",
    "Win32Gdi",
    "capture_available",
    "capture_full_screen",
    "capture_region",
    "capture_window",
    "png_dimensions",
    "resolve_capture_mode",
]
