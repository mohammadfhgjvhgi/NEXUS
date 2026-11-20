"""Native tool: ``clipboard`` (Final Build Plan §8.3).

Three operations — ``read`` · ``write`` · ``clear`` — with an honest
platform ladder:

* **Windows**: ``user32/kernel32`` clipboard via ctypes
  (OpenClipboard/GetClipboardData(CF_UNICODETEXT)/SetClipboardData);
* **Linux**: ``xclip`` or ``wl-copy``/``wl-paste`` when on PATH
  (subprocess, list-argv);
* otherwise unavailable — reported, never faked.

Clipboard is user-level ambient state: risk 1 (write mutates, read
observes — one tool, one level, the mutation is declared to the
Scope stage).

الحافظة — قراءة وكتابة ومسح بسلّم منصة صادق.

Stdlib only.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
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
    object_schema,
    output_schema,
    require_operation,
    require_str,
)

_OPERATIONS: tuple[str, ...] = ("read", "write", "clear")
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


def _linux_binary() -> tuple[list[str], list[str]] | None:
    """(write argv prefix, read argv) for the best Linux clipboard."""
    if shutil.which("xclip"):
        return (["xclip", "-selection", "clipboard"], ["xclip", "-o", "-selection", "clipboard"])
    if shutil.which("wl-copy"):
        return (["wl-copy"], ["wl-paste", "--no-newline"])
    return None


class ClipboardTool(NativeTool):
    """§8.3 ``clipboard`` — read/write/clear, risk 1."""

    name = "clipboard"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:clipboard",
            name=self.name,
            description=(
                "Clipboard capability: read, write(text), clear. "
                "Windows: ctypes clipboard; Linux: xclip/wl-clipboard."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "text": {"type": "string", "description": "text to write"},
                },
                required=("op",),
            ),
            output_schema=output_schema("clipboard text / write confirmation"),
            permissions=("clipboard.read", "clipboard.write"),
            scope_requirements=ScopeRequirements(
                path_arguments=(),
                mutating_operations=("write", "clear"),
                dimensions=("desktop",),
            ),
            risk=1,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        if operation == "write":
            return VerificationSpec(V.EXIT_ZERO)
        return VerificationSpec(V.NONE)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        if sys.platform == "win32":
            return self._windows(operation, arguments)
        ladder = _linux_binary()
        if ladder is None:
            raise _unavailable()
        write_argv, read_argv = ladder
        if operation == "read":
            completed = subprocess.run(  # noqa: S603 — fixed argv
                read_argv, capture_output=True, text=True, timeout=10, check=False
            )
            if completed.returncode != 0:
                return ToolCallResult(
                    output=f"clipboard read failed: {completed.stderr.strip()}",
                    artifacts={"exit_code": completed.returncode},
                )
            return ToolCallResult(
                output=completed.stdout,
                artifacts={"chars": len(completed.stdout)},
            )
        if operation == "clear":
            completed = subprocess.run(  # noqa: S603 — fixed argv
                ["printf", ""], input="", capture_output=True, text=True, check=False
            )
            _ = completed
            cleared = subprocess.run(  # noqa: S603 — fixed argv
                write_argv, input="", capture_output=True, text=True, check=False
            )
            return ToolCallResult(
                output="clipboard cleared" if cleared.returncode == 0 else "clear failed",
                artifacts={"exit_code": cleared.returncode},
            )
        text = require_str(arguments, "text")
        completed = subprocess.run(  # noqa: S603 — fixed argv
            write_argv, input=text, capture_output=True, text=True, check=False
        )
        return ToolCallResult(
            output=(
                f"wrote {len(text)} chars"
                if completed.returncode == 0
                else f"clipboard write failed: {completed.stderr.strip()}"
            ),
            artifacts={"exit_code": completed.returncode, "chars": len(text)},
        )

    # ------------------------------------------------------------- windows

    def _windows(
        self, operation: str, arguments: Mapping[str, Any]
    ) -> ToolCallResult:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not user32.OpenClipboard(None):
            return ToolCallResult(
                output="clipboard busy (OpenClipboard failed)",
                artifacts={"exit_code": 1},
            )
        try:
            if operation == "read":
                handle = user32.GetClipboardData(_CF_UNICODETEXT)
                if not handle:
                    return ToolCallResult(
                        output="(empty or non-text clipboard)",
                        artifacts={"exit_code": 0, "chars": 0},
                    )
                kernel32.GlobalLock.restype = ctypes.c_void_p
                locked = kernel32.GlobalLock(handle)
                try:
                    text = ctypes.wstring_at(locked)
                finally:
                    kernel32.GlobalUnlock(handle)
                return ToolCallResult(
                    output=text, artifacts={"exit_code": 0, "chars": len(text)}
                )
            if operation == "clear":
                ok = bool(user32.EmptyClipboard())
                return ToolCallResult(
                    output="clipboard cleared" if ok else "clear failed",
                    artifacts={"exit_code": 0 if ok else 1},
                )
            text = require_str(arguments, "text")
            user32.EmptyClipboard()
            size = (len(text) + 1) * ctypes.sizeof(ctypes.c_wchar)
            handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, size)
            kernel32.GlobalLock.restype = ctypes.c_void_p
            locked = kernel32.GlobalLock(handle)
            try:
                ctypes.memmove(
                    locked, ctypes.create_unicode_buffer(text), size
                )
            finally:
                kernel32.GlobalUnlock(handle)
            ok = bool(user32.SetClipboardData(_CF_UNICODETEXT, handle))
            return ToolCallResult(
                output=(
                    f"wrote {len(text)} chars"
                    if ok
                    else "SetClipboardData failed (clipboard owns no data)"
                ),
                artifacts={"exit_code": 0 if ok else 1, "chars": len(text)},
            )
        finally:
            user32.CloseClipboard()

    def capabilities(self) -> CapabilityReport:
        if sys.platform == "win32":
            return CapabilityReport(available=True, reason="ctypes clipboard")
        if _linux_binary() is not None:
            return CapabilityReport(
                available=True, reason="xclip/wl-clipboard on PATH"
            )
        return CapabilityReport(
            available=False,
            reason="no clipboard backend (win32 or xclip/wl-clipboard required)",
        )


def _unavailable() -> Exception:
    return ToolError()


class ToolError(Exception):
    """honest unavailable marker (formatted by the caller)."""

    def __init__(self) -> None:
        super().__init__(
            "clipboard unavailable: no backend on this platform "
            "(win32 or xclip/wl-clipboard required)"
        )
