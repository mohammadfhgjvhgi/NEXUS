"""Native tool: ``keyboard`` (Final Build Plan §9.1).

Synthetic keyboard via win32 ``SendInput``: ``press`` (a hotkey combo
like ``"ctrl+s"``, modifiers down-then-up in order) and ``type``
(arbitrary unicode through ``KEYEVENTF_UNICODE`` — UTF-16 surrogate
pairs for supplementary characters).

The packing lives in :mod:`._sendinput`; this module is the §8.1
record + the §8.2 contract. Honest unavailability off win32.

NEXUS rates synthetic keyboard injection risk 3: it types as the user
into whatever holds focus. The §9.5 hierarchy only reaches this layer
as the last resort.

لوحة المفاتيح الصناعية — مزيج ساخن أو نص يونيكود،
وخطر 3 لأنه يكتب باسم المستخدم.

Stdlib only.
"""

from __future__ import annotations

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
from ._sendinput import (
    InputError,
    combo_records,
    send,
    type_records,
)
from .base import (
    NativeTool,
    ToolArgError,
    object_schema,
    output_schema,
    require_operation,
)

_OPERATIONS: tuple[str, ...] = ("press", "type")


class KeyboardTool(NativeTool):
    """§9.1 ``keyboard`` — SendInput keys, risk 3."""

    name = "keyboard"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:keyboard",
            name=self.name,
            description=(
                "Synthetic keyboard (SendInput): press(combo='ctrl+s') and "
                "type(text) with full unicode support."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "combo": {
                        "type": "string",
                        "description": "key combo, e.g. ctrl+shift+t",
                    },
                    "text": {"type": "string", "description": "text to type"},
                },
                required=("op",),
            ),
            output_schema=output_schema("injection record count"),
            permissions=("input.inject",),
            scope_requirements=ScopeRequirements(
                path_arguments=(),
                mutating_operations=_OPERATIONS,
                dimensions=("display",),
            ),
            risk=3,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        return VerificationSpec(V.EXIT_ZERO)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        if sys.platform != "win32":
            raise ToolArgError(
                "op",
                "keyboard tool requires win32 SendInput "
                f"(this runtime is {sys.platform})",
            )
        if operation == "press":
            combo = arguments.get("combo")
            if not isinstance(combo, str) or not combo.strip():
                raise ToolArgError(
                    "combo", "a non-empty combo like 'ctrl+s' is required"
                )
            if "\x00" in combo:
                raise ToolArgError("combo", "null bytes are forbidden")
            try:
                records = combo_records(combo.strip())
            except InputError as exc:
                raise ToolArgError("combo", str(exc)) from exc
        else:
            text = arguments.get("text")
            if not isinstance(text, str):
                raise ToolArgError("text", "a string is required")
            if "\x00" in text:
                raise ToolArgError("text", "null bytes are forbidden")
            try:
                records = type_records(text)
            except InputError as exc:
                raise ToolArgError("text", str(exc)) from exc
        try:
            accepted = send(records)
        except InputError as exc:
            raise ToolArgError("op", str(exc)) from exc
        return ToolCallResult(
            output=f"keyboard {operation}: {accepted} input records accepted",
            artifacts={"op": operation, "records": accepted, "exit_code": 0},
        )

    def capabilities(self) -> CapabilityReport:
        if sys.platform == "win32":
            return CapabilityReport(
                available=True, reason="SendInput via ctypes"
            )
        return CapabilityReport(
            available=False,
            reason=f"win32-only (this runtime is {sys.platform})",
        )
