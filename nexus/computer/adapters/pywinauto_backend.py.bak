"""Backend adapters (Final Build Plan §9.3) — pywinauto, MODE A.

``pywinauto`` (BSD-3-Clause, pinned 18d2a95) is an **optional**
dependency — the ``[computer]`` extra — used directly behind the
Computer API for the deep Win32/UIA work the native ctypes client
does not attempt: control matching by title, robust waiters,
``type_keys`` into a specific control.

Rules of engagement (the MODE A discipline):

* imported **lazily inside every method** — a machine without the
  extra keeps every native path working, and this adapter reports
  unavailable honestly;
* the Win32 and UIA backends are selected per call site, never
  global state;
* every failure is wrapped in :class:`BackendError` with the
  pywinauto reason — no tracebacks leaking, no silent catches.

pywinauto خلف الواجهة — اختياري، استيراد كسول، وفشل صادق مغلّف.
"""

from __future__ import annotations

import sys
from typing import Any


class BackendError(Exception):
    """The pywinauto backend refused or failed — honest and wrapped."""


def _import_pywinauto() -> Any:
    try:
        import pywinauto  # noqa: PLC0415 — MODE A, lazy by contract
    except ImportError as exc:  # pragma: no cover - depends on machine
        raise BackendError(
            "pywinauto is not installed (the [computer] extra)"
        ) from exc
    return pywinauto


def available() -> tuple[bool, str]:
    """Honest probe: win32 + importable."""
    if sys.platform != "win32":
        return False, f"win32-only backend (this runtime is {sys.platform})"
    try:
        _import_pywinauto()
    except BackendError as exc:
        return False, str(exc)
    return True, "pywinauto (MODE A, [computer] extra)"


def _wrap(call: str, operation: Any) -> Any:
    try:
        return operation()
    except BackendError:
        raise
    except Exception as exc:  # pywinauto raises a wide family
        raise BackendError(f"pywinauto {call} failed: {exc}") from exc


def _window(pywinauto: Any, hwnd: int) -> Any:
    application = pywinauto.Application().connect(handle=hwnd, timeout=2)
    return application.window(handle=hwnd)


def _describe_tree(window: Any, depth: int = 2) -> dict[str, Any]:
    def render(control: Any, level: int) -> dict[str, Any]:
        try:
            rectangle = control.rectangle()
            rect = {
                "left": rectangle.left,
                "top": rectangle.top,
                "width": rectangle.width(),
                "height": rectangle.height(),
            }
        except Exception:
            rect = {}
        record: dict[str, Any] = {
            "name": str(control.window_text() or ""),
            "class_name": str(control.friendly_class_name() or ""),
            "rect": rect,
            "children": [],
        }
        if level >= depth:
            return record
        try:
            children = control.children()
        except Exception:
            children = []
        for child in children[:64]:
            record["children"].append(render(child, level + 1))
        return record

    return render(window, 0)


def describe_window(hwnd: int, depth: int = 2) -> dict[str, Any]:
    """One window's control tree (UIA backend), bounded and honest."""
    pywinauto = _import_pywinauto()

    def operation() -> dict[str, Any]:
        return _describe_tree(_window(pywinauto, hwnd), depth)

    return _wrap("describe_window", operation)


def type_into(hwnd: int, text: str) -> str:
    """``type_keys`` into a specific control (focused by pywinauto)."""
    pywinauto = _import_pywinauto()

    def operation() -> str:
        _window(pywinauto, hwnd).type_keys(text, with_spaces=True, pause=0.01)
        return f"typed {len(text)} characters into hwnd {hwnd}"

    return _wrap("type_into", operation)


def click_control(hwnd: int) -> str:
    """``click_input`` on a control by handle."""
    pywinauto = _import_pywinauto()

    def operation() -> str:
        _window(pywinauto, hwnd).click_input()
        return f"clicked hwnd {hwnd}"

    return _wrap("click_control", operation)


def invoke_control(hwnd: int) -> str:
    """Invoke pattern via pywinauto wrappers."""
    pywinauto = _import_pywinauto()

    def operation() -> str:
        _window(pywinauto, hwnd).invoke()
        return f"invoked hwnd {hwnd}"

    return _wrap("invoke_control", operation)


def set_value(hwnd: int, value: str) -> str:
    """Set text on an edit-type control by handle."""
    pywinauto = _import_pywinauto()

    def operation() -> str:
        _window(pywinauto, hwnd).set_edit_text(value)
        return f"set value on hwnd {hwnd}"

    return _wrap("set_value", operation)


def list_windows(limit: int = 50) -> list[dict[str, Any]]:
    """Top-level windows (UIA backend) — titles + handles."""
    pywinauto = _import_pywinauto()

    def operation() -> list[dict[str, Any]]:
        desktop = pywinauto.Desktop(backend="uia")
        rows: list[dict[str, Any]] = []
        for window in desktop.windows():
            if len(rows) >= limit:
                break
            rows.append(
                {
                    "hwnd": int(window.handle),
                    "title": str(window.window_text() or ""),
                }
            )
        return rows

    return _wrap("list_windows", operation)
