"""Input transports (Final Build Plan §9.2, ADAPTed).

Two transports, one honest contract, adapted (never imported) from
``browser-use/windows-harness`` ``inject.py``/``delivery.py`` design
(MIT, pinned 46a37cf):

* **foreground** — the foreground transport: take the target's
  foreground (with the AttachThreadInput assist when the OS refuses a
  bare ``SetForegroundWindow``), then ``SendInput`` the real events.
  Moves the user's cursor — the §9.5 last resort, and the transport
  says so.
* **message** — the background transport: ``PostMessageW`` the text to
  a specific window (``WM_CHAR`` per unit). Never activates the
  window, never steals focus — and refuses mouse semantics honestly
  (Chromium/WPF/UWP discard window-message clicks; pretending
  otherwise would be a silent no-op, the one thing NEXUS never does).

:class:`ForegroundError` separates "could not take the foreground"
from "could not inject" — the caller escalates or falls through, the
error never lies about which one happened.

نقلا الحقن — أمامي حقيقي أو خلفي مهذّب، ورفض صادق لما لا يعمل.

Stdlib only.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any

from ..tools.native._sendinput import (
    InputError,
    click_records,
    combo_records,
    move_records,
    send,
    type_records,
)

_WM_CHAR = 0x0102
_WM_CLOSE = 0x0010


class ForegroundError(Exception):
    """The foreground could not be taken (or given back) — honest."""


class TransportRefusedError(Exception):
    """The transport refuses this operation on this platform — honest."""


def _user32() -> Any:
    if sys.platform != "win32":
        return None
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _kernel32() -> Any:
    if sys.platform != "win32":
        return None
    return ctypes.windll.kernel32  # type: ignore[attr-defined]


def get_foreground() -> int:
    user32 = _user32()
    if user32 is None:
        raise TransportRefusedError(
            f"win32-only transport (this runtime is {sys.platform})"
        )
    return int(user32.GetForegroundWindow())


def ensure_foreground(hwnd: int) -> None:
    """Bring ``hwnd`` to the foreground or raise :class:`ForegroundError`.

    The bare ``SetForegroundWindow`` is refused by the OS when the
    caller is not the foreground process; the classic assist —
    temporarily attaching the input queues of the current and the
    target threads — is best-effort, and failure is reported, never
    swallowed.
    """
    user32 = _user32()
    if user32 is None:
        raise TransportRefusedError(
            f"win32-only transport (this runtime is {sys.platform})"
        )
    if int(user32.GetForegroundWindow()) == hwnd:
        return
    if int(user32.SetForegroundWindow(hwnd)):
        return
    kernel32 = _kernel32()
    current_thread = int(kernel32.GetCurrentThreadId())
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
    attached = False
    if target_thread and target_thread != current_thread:
        attached = bool(user32.AttachThreadInput(current_thread, target_thread, True))
    try:
        # A benign input nudge defeats the "recent input" gate.
        user32.keybd_event(0, 0, 2, 0)  # KEYEVENTF_KEYUP with VK_NULL
        if int(user32.SetForegroundWindow(hwnd)):
            return
        raise ForegroundError(
            f"SetForegroundWindow({hwnd}) refused even with AttachThreadInput"
        )
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def foreground_click(
    x: int, y: int, button: str = "left", *, count: int = 1
) -> int:
    """The foreground transport: real SendInput click at (x, y)."""
    return send(click_records(x, y, button, count=count))


def foreground_move(x: int, y: int) -> int:
    """The foreground transport: real SendInput move."""
    return send(move_records(x, y))


def foreground_type(text: str) -> int:
    """The foreground transport: real SendInput unicode typing."""
    return send(type_records(text))


def foreground_press(combo: str) -> int:
    """The foreground transport: a real SendInput hotkey."""
    return send(combo_records(combo))


def message_type(hwnd: int, text: str) -> int:
    """The background transport: WM_CHAR units posted to ``hwnd``.

    Works for classic Win32 edit-type windows; modern frameworks
    (Chromium, UWP, WPF with real input handling) ignore posted
    characters. Callers must verify or escalate — this transport is
    best-effort by design and honest about the count delivered.
    """
    user32 = _user32()
    if user32 is None:
        raise TransportRefusedError(
            f"win32-only transport (this runtime is {sys.platform})"
        )
    if "\x00" in text:
        raise InputError("null bytes are forbidden")
    if len(text) > 4096:
        raise InputError("message typing accepts at most 4096 characters")
    delivered = 0
    for character in text:
        for unit in _utf16_units(character):
            posted = int(
                user32.PostMessageW(
                    ctypes.c_void_p(hwnd), _WM_CHAR, unit, 0
                )
            )
            delivered += posted
    if delivered != len(list(text)):
        raise ForegroundError(
            f"WM_CHAR delivered {delivered} units — the target refused "
            "posted input (escalate to the foreground transport)"
        )
    return delivered


def message_click(hwnd: int, x: int, y: int) -> None:
    """Refused, honestly: window-message clicks are not universal."""
    raise TransportRefusedError(
        "message-transport mouse is refused: Chromium/WPF/UWP discard "
        "posted button messages — use the foreground transport"
    )


def _utf16_units(character: str) -> list[int]:
    code = ord(character)
    if code > 0xFFFF:
        code -= 0x10000
        return [0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)]
    return [code]


def available() -> bool:
    return sys.platform == "win32"
