"""Native tool foundation (Final Build Plan §8.3).

The nine native tools share this base: strict argument coercion
(:class:`ToolArgError` on bad input — data, not a crash), a uniform
``definition() / handler() / capabilities()`` triple, and honest
platform capability probes (the Phase-3 degradation ladder applied to
the tool surface: unavailable → reported, never faked).

الأدوات الأصلية التسع — قاعدة واحدة: تحقق صارم للمدخلات،
وإتاحة صادقة لكل منصة.

Stdlib only.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Mapping
from typing import Any

from ..models import (
    CapabilityReport,
    ToolCallResult,
    ToolDefinition,
    VerificationSpec,
)
from ..registry import ToolRegistry

#: Bounded default for subprocess-based tools (seconds).
DEFAULT_TIMEOUT_SECONDS = 30


class ToolArgError(Exception):
    """Bad tool arguments — an honest, actionable error for the agent."""

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"argument {key!r}: {reason}")
        self.key = key
        self.reason = reason


def require_str(
    arguments: Mapping[str, Any], key: str, *, default: str | None = None
) -> str:
    """Strict string argument (``ToolArgError`` on bad input)."""
    value = arguments.get(key, default)
    if not isinstance(value, str) or not value.strip():
        if default is None:
            raise ToolArgError(key, "a non-empty string is required")
        return default
    if "\x00" in value:
        raise ToolArgError(key, "null bytes are forbidden")
    return value


def optional_str(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ToolArgError(key, "must be a non-empty string without null bytes")
    return value


def require_int(
    arguments: Mapping[str, Any], key: str, *, default: int, low: int, high: int
) -> int:
    value = arguments.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolArgError(key, f"an integer in {low}..{high} is required")
    if not low <= value <= high:
        raise ToolArgError(key, f"must be within {low}..{high}")
    return value


def require_operation(arguments: Mapping[str, Any], allowed: tuple[str, ...]) -> str:
    operation = arguments.get("op")
    if operation not in allowed:
        raise ToolArgError("op", f"must be one of {list(allowed)}, got {operation!r}")
    return str(operation)


def object_schema(
    properties: Mapping[str, Any], *, required: tuple[str, ...] = ()
) -> dict[str, Any]:
    """The uniform §8.1 ``input_schema`` shape for native tools."""
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
    }


def output_schema(description: str) -> dict[str, Any]:
    """The uniform §8.1 ``output_schema`` shape for native tools."""
    return {"type": "object", "description": description}


class NativeTool:
    """One native tool's triple — subclass and override the members."""

    #: dispatch name (§8.3, verbatim)
    name: str = ""

    def definition(self) -> ToolDefinition:
        raise NotImplementedError

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        raise NotImplementedError

    def capabilities(self) -> CapabilityReport:
        return CapabilityReport(available=True, reason="always available")


def register_native_tool(registry: ToolRegistry, tool: NativeTool) -> None:
    """Register one native tool (id ``native:<name>``, version 1.0.0).

    When the tool implements ``verification_for(op)`` the registered
    handler refines the §8.1 verification contract per operation —
    the router stays the only verifier (§8.2).
    """
    resolver: Any = getattr(tool, "verification_for", None)

    def handler(arguments: Mapping[str, Any]) -> ToolCallResult:
        result = tool.handler(arguments)
        if callable(resolver) and arguments.get("op") is not None:
            spec = resolver(str(arguments.get("op")))
            if isinstance(spec, VerificationSpec):
                result.verify = spec
        return result

    registry.register(
        tool.definition(),
        handler,
        capability_probe=tool.capabilities,
    )


def on_windows() -> bool:
    return sys.platform == "win32"


def which_or_none(binary: str) -> str | None:
    return shutil.which(binary)
