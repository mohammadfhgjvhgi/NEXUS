"""Native tool: ``mouse`` (Final Build Plan §9.1).

Synthetic mouse via win32 ``SendInput`` (absolute coordinates against
the virtual screen): ``move`` · ``click`` · ``double_click`` ·
``right_click`` · ``middle_click`` · ``drag`` · ``scroll``.

The packing lives in :mod:`._sendinput` (the §9.2 ADAPT leaf); this
module is the §8.1 record + the §8.2 contract. On non-Windows the
capability probe reports unavailable honestly — the registry keeps the
tool, discovery says why, and no result is ever faked.

NEXUS rates synthetic pointer injection risk 3: it moves the user's
real cursor into whatever has focus. Confirmations and refusals stay
a §8.2 policy matter.

المؤشر الصناعي — SendInput بمعايرة الشاشة الافتراضية،
وخطر 3 لأنه يحرك مؤشر المستخدم الحقيقي.

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
    click_records,
    drag_records,
    move_records,
    scroll_records,
    send,
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
    "move",
    "click",
    "double_click",
    "right_click",
    "middle_click",
    "drag",
    "scroll",
)

_BUTTONS: tuple[str, ...] = ("left", "right", "middle")


def _point(arguments: Mapping[str, Any]) -> tuple[int, int]:
    for axis in ("x", "y"):
        value = arguments.get(axis)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolArgError(axis, "an integer coordinate is required")
        if not 0 <= value <= 65535:
            raise ToolArgError(axis, "must be within 0..65535")
    return int(arguments["x"]), int(arguments["y"])


def _button(arguments: Mapping[str, Any]) -> str:
    button = arguments.get("button", "left")
    if button not in _BUTTONS:
        raise ToolArgError("button", f"must be one of {list(_BUTTONS)}")
    return str(button)


def _send_packed(records: list[Any], operation: str) -> ToolCallResult:
    try:
        accepted = send(records)
    except InputError as exc:
        raise ToolArgError("op", str(exc)) from exc
    return ToolCallResult(
        output=f"mouse {operation}: {accepted} input records accepted",
        artifacts={"op": operation, "records": accepted, "exit_code": 0},
    )


class MouseTool(NativeTool):
    """§9.1 ``mouse`` — SendInput pointer, risk 3."""

    name = "mouse"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:mouse",
            name=self.name,
            description=(
                "Synthetic pointer (SendInput): move(x,y), click(x,y), "
                "double_click, right_click, middle_click, drag(x1,y1,x2,y2), "
                "scroll(units)."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "x": {"type": "integer", "description": "x pixel"},
                    "y": {"type": "integer", "description": "y pixel"},
                    "x1": {"type": "integer"},
                    "y1": {"type": "integer"},
                    "x2": {"type": "integer"},
                    "y2": {"type": "integer"},
                    "button": {"type": "string", "enum": list(_BUTTONS)},
                    "steps": {"type": "integer"},
                    "units": {"type": "integer", "description": "wheel units"},
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
                f"mouse tool requires win32 SendInput (this runtime is {sys.platform})",
            )
        if operation == "move":
            x, y = _point(arguments)
            return _send_packed(move_records(x, y), operation)
        if operation in ("click", "double_click", "right_click", "middle_click"):
            x, y = _point(arguments)
            button = {
                "click": "left",
                "double_click": "left",
                "right_click": "right",
                "middle_click": "middle",
            }[operation]
            count = 2 if operation == "double_click" else 1
            return _send_packed(
                click_records(x, y, button, count=count), operation
            )
        if operation == "drag":
            for axis in ("x1", "y1", "x2", "y2"):
                value = arguments.get(axis)
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ToolArgError(axis, "an integer coordinate is required")
                if not 0 <= value <= 65535:
                    raise ToolArgError(axis, "must be within 0..65535")
            steps = require_int(arguments, "steps", default=8, low=1, high=256)
            button = _button(arguments)
            return _send_packed(
                drag_records(
                    int(arguments["x1"]),
                    int(arguments["y1"]),
                    int(arguments["x2"]),
                    int(arguments["y2"]),
                    steps=steps,
                    button=button,
                ),
                operation,
            )
        # scroll
        units = require_int(arguments, "units", default=0, low=-1000, high=1000)
        return _send_packed(scroll_records(units), operation)

    def capabilities(self) -> CapabilityReport:
        if sys.platform == "win32":
            return CapabilityReport(
                available=True, reason="SendInput via ctypes"
            )
        return CapabilityReport(
            available=False,
            reason=f"win32-only (this runtime is {sys.platform})",
        )
