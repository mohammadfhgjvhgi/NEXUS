"""Tool System records (Final Build Plan §8.1).

The nine §8.1 fields, verbatim, on every tool::

    id
    name
    description
    input_schema
    output_schema
    permissions
    scope_requirements
    risk
    verification
    version

*:class:`ToolDefinition` is exactly that record (frozen, validated by
the :mod:`nexus.tools.registry`). ``risk`` rides the 0..4 danger
scale — the same five levels the platform's remote tool surface uses
(dl 0..4), so a NEXUS tool and a remote capability speak one risk
language. ``permissions`` are capability tags (``filesystem.write``,
``process.control`` …) the Tool Router gates; ``scope_requirements``
declare which arguments carry paths and which operations mutate, so
the Scope stage can route each call through the Phase-2 engine;
``verification`` is the §8.2 Verify stage's declarative contract.

Handlers return :class:`ToolCallResult` (output + artifacts); the
router normalizes that into a :class:`ToolOutcome` with the full
seven-stage :class:`RouterTrace` (§8.2, verbatim order).

سجلّات نظام الأدوات — الحقول التسعة حرفيًا، والمخاطر 0..4،
والتحقق تعاقديّ يعلّقه الموجّه في نهاية كل استدعاء.

Stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# ------------------------------------------------------------ §8.1 risk scale


class ToolRisk:
    """The 0..4 danger scale (mirrors the platform dl 0..4 levels).

    0 = pure read/observation · 1 = read + benign ambient state ·
    2 = scoped mutation · 3 = host-level execution · 4 = reserved
    (never granted remotely; NEXUS refuses to register level-4 tools).
    """

    SAFE = 0
    LOW = 1
    ELEVATED = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def label(cls, level: int) -> str:
        return {0: "safe", 1: "low", 2: "elevated", 3: "high", 4: "critical"}.get(
            level, "invalid"
        )


#: Valid risk levels — CRITICAL (4) is refused at registration (the
#: platform rule: level 4 is never granted, locally or remotely).
REGISTERABLE_RISK_LEVELS: tuple[int, ...] = (0, 1, 2, 3)

# ------------------------------------------------------- verification contract


class VerificationStrategy:
    """The §8.2 Verify stage's strategies (declarative, per tool).

    =================  =====================================================
    ``none``           verification not required (honest no-op — reported)
    ``path_exists``    artifact ``path`` must exist after the call
    ``path_size``      artifact ``path`` must exist and be non-empty
    ``output_nonempty``the normalized output must be non-empty
    ``exit_zero``      artifact ``exit_code`` must be exactly 0
    ``text_contains``  ``argument`` must appear in the output
    ``json_field``     artifact mapping under ``argument`` key must be truthy
    =================  =====================================================
    """

    NONE = "none"
    PATH_EXISTS = "path_exists"
    PATH_SIZE = "path_size"
    OUTPUT_NONEMPTY = "output_nonempty"
    EXIT_ZERO = "exit_zero"
    TEXT_CONTAINS = "text_contains"
    JSON_FIELD = "json_field"

    ALL: tuple[str, ...] = (
        NONE,
        PATH_EXISTS,
        PATH_SIZE,
        OUTPUT_NONEMPTY,
        EXIT_ZERO,
        TEXT_CONTAINS,
        JSON_FIELD,
    )


@dataclass(frozen=True, slots=True)
class VerificationSpec:
    """The ``verification`` field of §8.1 — strategy + one argument."""

    strategy: str = VerificationStrategy.NONE
    argument: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"strategy": self.strategy, "argument": self.argument}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Outcome of the Verify stage — attached to every ToolOutcome."""

    strategy: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "passed": self.passed,
            "detail": self.detail,
        }


# ---------------------------------------------------------- scope requirements


@dataclass(frozen=True, slots=True)
class ScopeRequirements:
    """The ``scope_requirements`` field of §8.1.

    * ``path_arguments`` — argument names that carry filesystem paths
      the Scope stage must resolve (read vs. mutate per operation);
    * ``mutating_operations`` — values of the ``op`` argument that
      change the world (scoped WRITE instead of READ);
    * ``dimensions`` — the §3.2 scope dimensions the tool touches
      (``filesystem`` · ``network`` · ``process`` · ``display`` ·
      ``git`` · ``external``) — descriptive, used by discovery.
    """

    path_arguments: tuple[str, ...] = ()
    mutating_operations: tuple[str, ...] = ()
    dimensions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_arguments": list(self.path_arguments),
            "mutating_operations": list(self.mutating_operations),
            "dimensions": list(self.dimensions),
        }


# ------------------------------------------------------------- §8.1 the record


_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def is_valid_version(text: str) -> bool:
    """Strict ``X.Y.Z`` version check (the §8.1 ``version`` contract)."""
    return bool(_VERSION_RE.match(text))


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """One tool — the §8.1 nine fields, verbatim (id … version)."""

    id: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    permissions: tuple[str, ...]
    scope_requirements: ScopeRequirements
    risk: int
    verification: VerificationSpec
    version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "permissions": list(self.permissions),
            "scope_requirements": self.scope_requirements.to_dict(),
            "risk": self.risk,
            "risk_label": ToolRisk.label(self.risk),
            "verification": self.verification.to_dict(),
            "version": self.version,
        }


#: The §8.1 field names, verbatim order (registry validation is exact).
TOOL_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "description",
    "input_schema",
    "output_schema",
    "permissions",
    "scope_requirements",
    "risk",
    "verification",
    "version",
)

# ---------------------------------------------------------------- call results


@dataclass(slots=True)
class ToolCallResult:
    """What a tool handler returns: output + artifacts.

    ``artifacts`` carry the values the Verify stage needs (``path``,
    ``exit_code``, …) — plain data, no behavior. ``verify`` optionally
    refines the §8.1 ``verification`` contract per operation (the
    definition's spec stays the default; the router is still the only
    verifier).
    """

    output: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    verify: VerificationSpec | None = None


@dataclass(frozen=True, slots=True)
class TraceEntry:
    """One stage of the §8.2 pipeline — (stage, status, detail)."""

    stage: str
    status: str  # "info" | "pass" | "fail" | "skip" | "confirmed"
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"stage": self.stage, "status": self.status, "detail": self.detail}


#: The §8.2 pipeline, verbatim order — the trace proves it.
ROUTER_STAGES: tuple[str, ...] = (
    "agent",
    "discovery",
    "permission",
    "scope",
    "resource",
    "execute",
    "normalize",
    "verify",
)

#: The seven §8.2 stages after the agent entry point.
PIPELINE_STAGES: tuple[str, ...] = ROUTER_STAGES[1:]


@dataclass(frozen=True, slots=True)
class RouterTrace:
    """The ordered stage record of one routed call (§8.2, verbatim)."""

    entries: tuple[TraceEntry, ...] = ()

    def stages(self) -> tuple[str, ...]:
        return tuple(entry.stage for entry in self.entries)

    def to_dict(self) -> list[dict[str, str]]:
        return [entry.to_dict() for entry in self.entries]


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """Normalized result of one routed tool call (§8.2 «Normalize»).

    ``ok`` is the final verdict *after* the Verify stage — a handler
    that claims success but fails verification is a failure here.
    """

    tool: str
    ok: bool
    output: str = ""
    error: str = ""
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    verification: VerificationReport | None = None
    trace: RouterTrace | None = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "artifacts": dict(self.artifacts),
            "verification": (
                self.verification.to_dict() if self.verification else None
            ),
            "trace": self.trace.to_dict() if self.trace else None,
            "elapsed_ms": self.elapsed_ms,
        }


# -------------------------------------------------------- capability reporting


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """Honest platform availability for one tool (degradation ladder)."""

    available: bool
    reason: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "detail": dict(self.detail),
        }


class ToolError(Exception):
    """A tool's honest failure — data for the agent, never a crash."""
