"""Native tool: ``uia`` (Final Build Plan §9.1 / §9.4).

The UI Automation surface over the NEXUS-owned :mod:`ctypes` client
(:mod:`nexus.computer.uia_native`, imported lazily — the §0.4 seams):

``inspect`` (a bounded element tree from the root or a handle) ·
``element`` (one element record) · ``focused`` (the focused element) ·
``invoke`` (the Invoke pattern) · ``set_value`` (the Value pattern) ·
``focus`` (element SetFocus — complements the ``windows`` tool's
``SetForegroundWindow``).

Reads are risk 1; ``invoke``/``set_value``/``focus`` mutate UI state —
the tool record carries risk 2 (the §8.2 gate, not a silent surprise).
Off win32 the capability probe reports unavailable honestly.

أتمتة الواجهة الأصلية — شجرة عناصر وأنماط، أول طبقة قبل أي مكتبة.

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
from .base import (
    NativeTool,
    ToolArgError,
    object_schema,
    output_schema,
    require_int,
    require_operation,
)

_OPERATIONS: tuple[str, ...] = (
    "inspect",
    "element",
    "focused",
    "invoke",
    "set_value",
    "focus",
)

_MUTATING: tuple[str, ...] = ("invoke", "set_value", "focus")


def _uia_native() -> Any:
    # Lazy (§0.4): imported at call time, never at module import time.
    from ...computer import uia_native

    return uia_native


def _from_handle_or_root(uia: Any, arguments: Mapping[str, Any]) -> Any:
    hwnd = arguments.get("hwnd")
    if hwnd is None:
        return uia.root_element()
    if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd < 1:
        raise ToolArgError("hwnd", "a positive window handle is required")
    return uia.element_from_handle(hwnd)


class UiaTool(NativeTool):
    """§9.1 ``uia`` — native UI Automation, risk 2."""

    name = "uia"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:uia",
            name=self.name,
            description=(
                "Windows UI Automation (native ctypes client): inspect"
                "(hwnd?, depth, max_nodes), element(hwnd), focused(), "
                "invoke(hwnd), set_value(hwnd, value), focus(hwnd)."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "hwnd": {"type": "integer", "description": "window handle"},
                    "depth": {"type": "integer", "description": "tree depth 1..8"},
                    "max_nodes": {"type": "integer", "description": "node bound"},
                    "value": {"type": "string", "description": "value to set"},
                },
                required=("op",),
            ),
            output_schema=output_schema("element record / tree / control result"),
            permissions=("uia.read", "uia.control"),
            scope_requirements=ScopeRequirements(
                path_arguments=(),
                mutating_operations=_MUTATING,
                dimensions=("display",),
            ),
            risk=2,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        if operation in ("inspect",):
            return VerificationSpec(V.JSON_FIELD, "tree")
        if operation in ("element", "focused"):
            return VerificationSpec(V.JSON_FIELD, "element")
        return VerificationSpec(V.EXIT_ZERO)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        if sys.platform != "win32":
            raise ToolArgError(
                "op",
                f"uia tool requires win32 UIA (this runtime is {sys.platform})",
            )
        uia = _uia_native()
        if operation == "inspect":
            depth = require_int(arguments, "depth", default=2, low=1, high=8)
            max_nodes = require_int(arguments, "max_nodes", default=64, low=1, high=500)
            element = _from_handle_or_root(uia, arguments)
            try:
                tree = uia.tree_record(element, depth=depth, max_nodes=max_nodes)
            finally:
                element.release()
            return ToolCallResult(
                output=self._render(tree),
                artifacts={"tree": tree},
            )
        if operation == "element":
            hwnd = arguments.get("hwnd")
            if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd < 1:
                raise ToolArgError("hwnd", "a positive window handle is required")
            element = uia.element_from_handle(hwnd)
            try:
                record = element.record()
            finally:
                element.release()
            return ToolCallResult(
                output=self._render(record), artifacts={"element": record}
            )
        if operation == "focused":
            element = uia.focused_element()
            try:
                record = element.record()
            finally:
                element.release()
            return ToolCallResult(
                output=self._render(record), artifacts={"element": record}
            )
        # invoke / set_value / focus
        hwnd = arguments.get("hwnd")
        if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd < 1:
            raise ToolArgError("hwnd", "a positive window handle is required")
        if operation == "set_value":
            value = arguments.get("value")
            if not isinstance(value, str):
                raise ToolArgError("value", "a string is required")
            if "\x00" in value:
                raise ToolArgError("value", "null bytes are forbidden")
        element = uia.element_from_handle(hwnd)
        try:
            if operation == "invoke":
                element.invoke()
            elif operation == "set_value":
                element.set_value(value)
            else:
                element.set_focus()
        finally:
            element.release()
        return ToolCallResult(
            output=f"uia {operation} → hwnd {hwnd}: ok",
            artifacts={"op": operation, "hwnd": hwnd, "exit_code": 0},
        )

    def _render(self, record: Mapping[str, Any]) -> str:
        lines: list[str] = []

        def emit(node: Mapping[str, Any], indent: int) -> None:
            name = str(node.get("name", ""))[:60] or "(unnamed)"
            type_name = str(node.get("control_type_name", "unknown"))
            lines.append(f"{'  ' * indent}- {type_name}: {name}")
            for child in node.get("children", ()):
                emit(child, indent + 1)

        emit(record, 0)
        return "\n".join(lines) if lines else "(empty tree)"

    def capabilities(self) -> CapabilityReport:
        if sys.platform == "win32":
            return CapabilityReport(
                available=True, reason="native UIA via ctypes COM"
            )
        return CapabilityReport(
            available=False,
            reason=f"win32-only (this runtime is {sys.platform})",
        )
