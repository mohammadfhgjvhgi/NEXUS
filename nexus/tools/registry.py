"""Tool Registry (Final Build Plan §8.1).

Every capability enters NEXUS through here as one :class:`ToolDefinition`
— the nine §8.1 fields, validated exactly:

* ``id`` non-empty, unique; ``name`` non-empty, unique (the dispatch key);
* ``input_schema`` a JSON-object contract (``type: object`` +
  ``properties`` mapping); ``output_schema`` a typed mapping;
* ``permissions`` at least one non-empty capability tag;
* ``risk`` an int in 0..4 — level 4 (CRITICAL) is refused outright
  (the platform rule: level 4 is never granted);
* ``version`` strict ``X.Y.Z``; a re-registration under the same name
  must be an upgrade (strictly higher), never a silent replace;
* ``scope_requirements`` / ``verification`` the typed records.

Handlers return :class:`ToolCallResult`; each tool may register a
``capabilities()`` probe (honest platform availability — the Phase-3
degradation ladder applied to tools).

The registry is freezable: after wiring, ``freeze()`` turns any
mutation into an error (the runtime's tool surface is then closed).

سجلّ الأدوات — كل قدرة تدخل من هنا، بتسعة حقول مُتحقَّقة،
والترقية فقط، والتجميد بعد التوصيل.

Stdlib only.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import (
    REGISTERABLE_RISK_LEVELS,
    CapabilityReport,
    ToolCallResult,
    ToolDefinition,
    is_valid_version,
)

logger = logging.getLogger("nexus.tools")

#: Handler contract: arguments mapping → call result (raises → honest failure).
ToolHandler = Callable[[Mapping[str, Any]], ToolCallResult]
#: Capability probe contract: no arguments → honest availability.
CapabilityProbe = Callable[[], CapabilityReport]


class RegistryError(Exception):
    """Invalid registration — the §8.1 contract was violated."""


@dataclass(slots=True)
class RegisteredTool:
    """A definition + its handler + optional capability probe."""

    definition: ToolDefinition
    handler: ToolHandler
    capability_probe: CapabilityProbe | None = None

    def capabilities(self) -> CapabilityReport:
        if self.capability_probe is None:
            return CapabilityReport(available=True, reason="always available")
        return self.capability_probe()


def _validate_definition(definition: ToolDefinition) -> None:
    """The exact §8.1 contract — raise RegistryError with a precise field."""
    problems: list[str] = []
    for name in ("id", "name", "description"):
        value = getattr(definition, name)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{name} must be a non-empty string")
    schema = definition.input_schema
    if not isinstance(schema, Mapping) or "type" not in schema:
        problems.append("input_schema must be a mapping with a 'type' key")
    elif schema["type"] != "object" or not isinstance(
        schema.get("properties"), Mapping
    ):
        problems.append("input_schema must be {type: object, properties: {...}}")
    if not isinstance(definition.output_schema, Mapping) or not definition.output_schema:
        problems.append("output_schema must be a non-empty mapping")
    permissions = definition.permissions
    if (
        not isinstance(permissions, tuple)
        or not permissions
        or any(not isinstance(tag, str) or not tag.strip() for tag in permissions)
    ):
        problems.append("permissions must be a non-empty tuple of non-empty strings")
    if not isinstance(definition.risk, int) or isinstance(definition.risk, bool):
        problems.append("risk must be an int")
    elif definition.risk not in REGISTERABLE_RISK_LEVELS:
        problems.append(
            f"risk must be one of {REGISTERABLE_RISK_LEVELS} "
            "(level 4 CRITICAL is never grantable)"
        )
    if not is_valid_version(definition.version):
        problems.append(f"version {definition.version!r} must be strict X.Y.Z")
    if problems:
        raise RegistryError(f"invalid tool {definition.name!r}: " + "; ".join(problems))


def _version_tuple(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


class ToolRegistry:
    """The §8.1 registry — validated, version-aware, freezable."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._frozen = False

    # ------------------------------------------------------------ mutation

    def register(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
        *,
        capability_probe: CapabilityProbe | None = None,
        replace: bool = False,
    ) -> RegisteredTool:
        """Register one tool (validated); same-name registration must be
        an upgrade (strictly higher version) unless ``replace``."""
        if self._frozen:
            raise RegistryError("registry is frozen — no mutations")
        _validate_definition(definition)
        existing = self._tools.get(definition.name)
        if existing is not None:
            if _version_tuple(definition.version) <= _version_tuple(
                existing.definition.version
            ) and not replace:
                raise RegistryError(
                    f"duplicate tool {definition.name!r}: version "
                    f"{definition.version} must be strictly higher than "
                    f"{existing.definition.version} (no silent replace)"
                )
            logger.info(
                "tool %s upgraded %s → %s",
                definition.name,
                existing.definition.version,
                definition.version,
            )
        registered = RegisteredTool(
            definition=definition,
            handler=handler,
            capability_probe=capability_probe,
        )
        self._tools[definition.name] = registered
        return registered

    def unregister(self, name: str) -> bool:
        """Remove one tool by name; returns whether it existed."""
        if self._frozen:
            raise RegistryError("registry is frozen — no mutations")
        return self._tools.pop(name, None) is not None

    def freeze(self) -> None:
        """Close the registry (the runtime's tool surface is wired)."""
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    # ----------------------------------------------------------- discovery

    def get(self, name: str) -> RegisteredTool | None:
        """Exact lookup by dispatch name (the §8.2 «Tool discovery»)."""
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(entry.definition for entry in self._tools.values())

    def discover(
        self,
        *,
        available_only: bool = False,
        permission: str | None = None,
        dimension: str | None = None,
    ) -> tuple[ToolDefinition, ...]:
        """Discovery view: filter by availability, permission tag or
        scope dimension (the agent-facing catalogue)."""
        results: list[ToolDefinition] = []
        for entry in self._tools.values():
            if available_only and not entry.capabilities().available:
                continue
            if (
                permission is not None
                and permission not in entry.definition.permissions
            ):
                continue
            if (
                dimension is not None
                and dimension not in entry.definition.scope_requirements.dimensions
            ):
                continue
            results.append(entry.definition)
        return tuple(results)

    def capabilities(self, name: str) -> CapabilityReport | None:
        entry = self._tools.get(name)
        return None if entry is None else entry.capabilities()

    # -------------------------------------------------------------- counts

    def count(self) -> int:
        return len(self._tools)

    def families(self) -> dict[str, int]:
        """Counts by id prefix — ``native:`` vs ``mcp:<server>:``."""
        counts: dict[str, int] = {}
        for entry in self._tools.values():
            family = entry.definition.id.split(":", 1)[0] or "unknown"
            counts[family] = counts.get(family, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count(),
            "families": self.families(),
            "frozen": self._frozen,
            "tools": [entry.definition.to_dict() for entry in self._tools.values()],
        }
