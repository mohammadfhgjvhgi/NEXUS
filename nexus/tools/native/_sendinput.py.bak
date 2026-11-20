"""SendInput engine (Final Build Plan §9.2, ADAPTed).

The win32 ``SendInput`` syscall packing — structures, flags, coordinate
normalisation and key-name table — as a dependency-free leaf shared by
the ``mouse`` and ``keyboard`` §9.1 tools and the §9.5 input layer.

Design adapted (not imported) from ``browser-use/windows-harness``
``inject.py`` (MIT, 2026 — pinned 46a37cf): one contract for synthetic
input, honest failure when the platform refuses, absolute coordinates
normalised against the **virtual** screen, and unicode typing via
``KEYEVENTF_UNICODE``. NEXUS owns every line here.

NEXUS rates synthetic input injection risk 3 — it types and clicks as
the user, into whatever has focus. Level-4-style total refusal stays
a §8.2 policy matter; the packing itself is mechanics.

حقن المدخلات الصناعية — التعبئة والمعايرة وجدول المفاتيح،
بلا تبعيات، وفشل صادق عند رفض المنصة.

Stdlib only (``ctypes`` is stdlib).
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Mapping
from typing import Any

#: INPUT type discriminator (winuser.h).
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# MOUSEEVENTF_* flags (winuser.h)
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000

# KEYEVENTF_* flags (winuser.h)
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# GetSystemMetrics indices
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

WHEEL_DELTA = 120

#: Virtual-key table by lower-case key name (winuser.h VK_*).
KEY_NAMES: dict[str, int] = {
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "menu": 0x12,
    "win": 0x5B,
    "super": 0x5B,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "bs": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "apps": 0x5D,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
}
for _offset in range(26):
    KEY_NAMES[chr(ord("a") + _offset)] = 0x41 + _offset
for _offset in range(10):
    KEY_NAMES[str(_offset)] = 0x30 + _offset
for _offset in range(12):
    KEY_NAMES[f"f{_offset + 1}"] = 0x70 + _offset


class InputError(Exception):
    """SendInput refused or failed — honest, actionable, never silent."""


class _MOUSEINPUT(ctypes.Structure):
    """winuser ``MOUSEINPUT`` — explicit widths (LONG=4, DWORD=4,
    ULONG_PTR=pointer-sized): the layout stays byte-exact on every
    platform, not just where ``c_long`` happens to be 4 bytes."""

    _fields_ = [
        ("dx", ctypes.c_int32),
        ("dy", ctypes.c_int32),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    """winuser ``KEYBDINPUT`` — explicit widths (same discipline)."""

    _fields_ = [
        ("wVk", ctypes.c_uint16),
        ("wScan", ctypes.c_uint16),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class INPUT(ctypes.Structure):
    """The winuser ``INPUT`` record (mouse or keyboard)."""

    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTUNION)]


def _user32() -> Any:
    if sys.platform != "win32":
        return None
    return ctypes.windll.user32  # type: ignore[attr-defined]


def on_windows() -> bool:
    return sys.platform == "win32"


def virtual_screen() -> tuple[int, int, int, int]:
    """(x, y, width, height) of the whole virtual screen."""
    user32 = _user32()
    if user32 is None:
        raise InputError(
            f"SendInput requires win32 (this runtime is {sys.platform})"
        )
    x = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    y = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    return x, y, width, height


def normalise_point(
    x: int, y: int, screen: tuple[int, int, int, int] | None = None
) -> tuple[int, int]:
    """Map a virtual-screen pixel point to 0..65535 absolute mickeys.

    ``screen`` (origin_x, origin_y, width, height) may be injected —
    the mapping itself is pure geometry; without it the live virtual
    screen is queried (win32-only, honest refusal elsewhere).
    """
    if screen is None:
        screen = virtual_screen()
    origin_x, origin_y, width, height = screen
    span_x = max(width - 1, 1)
    span_y = max(height - 1, 1)
    mickey_x = (x - origin_x) * 65535 // span_x
    mickey_y = (y - origin_y) * 65535 // span_y
    return (
        max(0, min(65535, mickey_x)),
        max(0, min(65535, mickey_y)),
    )


def send(inputs: list[INPUT]) -> int:
    """Dispatch packed INPUT records; returns the count SendInput accepted.

    ``SendInput`` returning fewer records than sent means an input-block
    (UIPI on an elevated target, or a hook swallowing the batch) — that
    is an honest :class:`InputError`, never a silent no-op.
    """
    user32 = _user32()
    if user32 is None:
        raise InputError(
            f"SendInput requires win32 (this runtime is {sys.platform})"
        )
    if not inputs:
        return 0
    array = (INPUT * len(inputs))(*inputs)
    accepted = int(
        user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    )
    if accepted != len(inputs):
        raise InputError(
            f"SendInput accepted {accepted}/{len(inputs)} records — "
            "the target likely blocks synthetic input (UIPI/elevation)"
        )
    return accepted


def mouse_record(
    *, mickey_x: int, mickey_y: int, flags: int, data: int = 0
) -> INPUT:
    """One mouse INPUT (absolute coordinates + event flags)."""
    record = INPUT()
    record.type = INPUT_MOUSE
    record.union.mi.dx = mickey_x
    record.union.mi.dy = mickey_y
    record.union.mi.mouseData = data & 0xFFFFFFFF
    record.union.mi.dwFlags = flags
    return record


def move_records(
    x: int, y: int, screen: tuple[int, int, int, int] | None = None
) -> list[INPUT]:
    """Absolute move to virtual-screen pixel (x, y)."""
    mickey_x, mickey_y = normalise_point(x, y, screen)
    return [
        mouse_record(
            mickey_x=mickey_x,
            mickey_y=mickey_y,
            flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
        )
    ]


def button_records(button: str, *, press: bool) -> list[INPUT]:
    """One button press or release (left/right/middle)."""
    table = {
        ("left", True): MOUSEEVENTF_LEFTDOWN,
        ("left", False): MOUSEEVENTF_LEFTUP,
        ("right", True): MOUSEEVENTF_RIGHTDOWN,
        ("right", False): MOUSEEVENTF_RIGHTUP,
        ("middle", True): MOUSEEVENTF_MIDDLEDOWN,
        ("middle", False): MOUSEEVENTF_MIDDLEUP,
    }
    key = (button, press)
    if key not in table:
        raise InputError(
            f"button must be left/right/middle, got {button!r}"
        )
    return [
        mouse_record(
            mickey_x=0, mickey_y=0, flags=table[key]
        )
    ]


def click_records(
    x: int,
    y: int,
    button: str,
    *,
    count: int = 1,
    screen: tuple[int, int, int, int] | None = None,
) -> list[INPUT]:
    """Move + press/release cycles at (x, y)."""
    if count not in (1, 2):
        raise InputError("click count must be 1 or 2 (double-click)")
    records = move_records(x, y, screen)
    for _ in range(count):
        records += button_records(button, press=True)
        records += button_records(button, press=False)
    return records


def drag_records(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    steps: int = 8,
    button: str = "left",
    screen: tuple[int, int, int, int] | None = None,
) -> list[INPUT]:
    """Press at (x1, y1), move in steps, release at (x2, y2)."""
    if steps < 1 or steps > 256:
        raise InputError("drag steps must be within 1..256")
    records = move_records(x1, y1, screen)
    records += button_records(button, press=True)
    for index in range(1, steps + 1):
        fraction = index / steps
        intermediate_x = round(x1 + (x2 - x1) * fraction)
        intermediate_y = round(y1 + (y2 - y1) * fraction)
        records += move_records(intermediate_x, intermediate_y, screen)
    records += button_records(button, press=False)
    return records


def scroll_records(units: int) -> list[INPUT]:
    """Vertical wheel scroll (positive = up, negative = down)."""
    if not -1000 <= units <= 1000:
        raise InputError("scroll units must be within -1000..1000")
    return [
        mouse_record(
            mickey_x=0,
            mickey_y=0,
            flags=MOUSEEVENTF_WHEEL,
            data=units * WHEEL_DELTA,
        )
    ]


def key_record(vk: int, *, press: bool) -> INPUT:
    """One virtual-key press/release record."""
    record = INPUT()
    record.type = INPUT_KEYBOARD
    record.union.ki.wVk = vk & 0xFFFF
    record.union.ki.dwFlags = 0 if press else KEYEVENTF_KEYUP
    return record


def parse_combo(combo: str) -> tuple[list[int], int]:
    """Split ``"ctrl+shift+t"`` into (modifiers, final key) VK codes."""
    parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
    if not parts:
        raise InputError("combo must name at least one key")
    if len(parts) > 8:
        raise InputError("combo supports at most 8 keys")
    codes = []
    for part in parts:
        if part not in KEY_NAMES:
            raise InputError(f"unknown key name {part!r} in combo")
        codes.append(KEY_NAMES[part])
    modifiers, final = codes[:-1], codes[-1]
    return modifiers, final


def combo_records(combo: str) -> list[INPUT]:
    """Full press-then-release sequence for one hotkey combo."""
    modifiers, final = parse_combo(combo)
    records: list[INPUT] = []
    for vk in modifiers:
        records.append(key_record(vk, press=True))
    records.append(key_record(final, press=True))
    records.append(key_record(final, press=False))
    for vk in reversed(modifiers):
        records.append(key_record(vk, press=False))
    return records


def _surrogate_pairs(text: str) -> list[int]:
    """Code points, with supplementary characters split to UTF-16 pairs."""
    units: list[int] = []
    for character in text:
        code = ord(character)
        if code > 0xFFFF:
            code -= 0x10000
            units.append(0xD800 + (code >> 10))
            units.append(0xDC00 + (code & 0x3FF))
        else:
            units.append(code)
    return units


def type_records(text: str) -> list[INPUT]:
    """Unicode typing — per character, all KEYEVENTF_UNICODE downs
    then all ups (a surrogate pair's downs stay adjacent so the OS
    decodes the pair; splitting down/up per unit would break it)."""
    if len(text) > 4096:
        raise InputError("type accepts at most 4096 characters")
    records: list[INPUT] = []
    for character in text:
        units = _surrogate_pairs(character)
        for unit in units:
            records.append(_unicode_record(unit, press=True))
        for unit in units:
            records.append(_unicode_record(unit, press=False))
    return records


def _unicode_record(unit: int, *, press: bool) -> INPUT:
    record = INPUT()
    record.type = INPUT_KEYBOARD
    record.union.ki.wVk = 0
    record.union.ki.wScan = unit
    record.union.ki.dwFlags = (
        (0 if press else KEYEVENTF_KEYUP) | KEYEVENTF_UNICODE
    )
    return record


def coerce_point(
    arguments: Mapping[str, Any], axis: str
) -> int:
    """Strict integer coordinate (0..65535 honest bound)."""
    value = arguments.get(axis)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"argument {axis!r}: an integer coordinate is required")
    if not 0 <= value <= 65535:
        raise InputError(f"argument {axis!r}: must be within 0..65535")
    return value
