"""Execution Gates (New Plan §21.3–§21.5) + the admission pipeline.

Three gates, verbatim::

    21.3 Tool Gate    — every named tool through scope+policy+risk
    21.4 MCP Gate     — every MCP server:tool pair through its registry
    21.5 Plugin Gate  — every plugin through its *declared* permissions

All three speak one contract (:class:`GateDecision`) and feed one
pipeline: **GatePipeline.admit** walks the v0.1 §57 order — scope
check → permission check → gate check → audit — and the audit record
is written for *every* verdict (deny included): there is no hidden
enforcement, and nothing executes without a decision that allows it.

Default postures, honestly conservative where the plan demands it:

* Tool Gate — a blocked tool is denied, an unregistered tool is
  escalated (never silently allowed).
* MCP Gate — a blocked server is denied, an unregistered server is
  escalated, a tool outside its server's allow-list is escalated.
* Plugin Gate — a plugin asking for *secrets* access is denied unless
  secrets were explicitly granted (§21.6's reference law is not a
  plugin default); unregistered plugins are escalated.

بوابات التنفيذ الثلاث بخط أنابيب واحد: نطاق ← إذن ← بوابة ← تدقيق،
وكل حكم — حتى المنع — مكتوب في السجل.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.policy.models import TaskPolicy
from ..core.scope.models import Scope
from ..core.workspace.manager import WorkspaceManager
from .audit import AuditLog
from .contracts import (
    GateDecision,
    GateVerdict,
    RiskLevel,
    SecurityAction,
    SecurityError,
)
from .permissions import PermissionEngine


def _decision(
    action: SecurityAction,
    gate: str,
    verdict: GateVerdict,
    rule: str,
    reason: str,
    risk: RiskLevel,
) -> GateDecision:
    return GateDecision(
        action=action, verdict=verdict, risk=risk, gate=gate, rule=rule, reason=reason
    )


def _risk_of(
    action: SecurityAction, risks: Mapping[str, RiskLevel], default: RiskLevel
) -> RiskLevel:
    if action.risk_hint is not None:
        return action.risk_hint
    return risks.get(action.name, risks.get(action.name.lower(), default))


# ------------------------------------------------------------------ §21.3


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    """One registered tool — its §163 risk and its confirm-first flag."""

    name: str
    risk: RiskLevel = RiskLevel.MEDIUM
    confirm_first: bool = False


class ToolGate:
    """§21.3 — the Tool Gate."""

    id = "tool-gate"

    def __init__(
        self,
        *,
        allowed: Iterable[str] = ("*",),
        blocked: Iterable[str] = (),
        confirm: Iterable[str] = (),
        risks: Mapping[str, RiskLevel] | None = None,
    ) -> None:
        self._allowed = tuple(t.strip() for t in allowed if t.strip())
        self._blocked = frozenset(t.strip().lower() for t in blocked if t.strip())
        self._confirm = frozenset(t.strip().lower() for t in confirm if t.strip())
        self._risks: dict[str, RiskLevel] = {
            k.lower(): v for k, v in (risks or {}).items()
        }
        self._registry: dict[str, ToolRegistration] = {}

    def register(
        self,
        name: str,
        *,
        risk: RiskLevel = RiskLevel.MEDIUM,
        confirm_first: bool = False,
    ) -> ToolRegistration:
        """Register a tool with its §163 risk (declared, not assumed)."""
        entry = ToolRegistration(name=name.strip(), risk=risk, confirm_first=confirm_first)
        self._registry[entry.name.lower()] = entry
        return entry

    def evaluate(self, action: SecurityAction) -> GateDecision:
        """One tool action → its gate decision (audit record)."""
        if action.kind != "tool":
            raise SecurityError(f"ToolGate admits kind 'tool', got {action.kind!r}")
        name = action.name.strip()
        lowered = name.lower()
        risk = _risk_of(
            action,
            {k: e.risk for k, e in self._registry.items()} | self._risks,
            RiskLevel.MEDIUM,
        )
        if lowered in self._blocked:
            return _decision(
                action, "tool", GateVerdict.DENY, "tool-blocked",
                f"tool {name!r} is on the blocked list", risk,
            )
        confirm_first = self._registry.get(lowered)
        if confirm_first is not None and confirm_first.confirm_first:
            return _decision(
                action, "tool", GateVerdict.CONFIRM, "tool-confirm-first",
                f"tool {name!r} is marked confirm-first", risk,
            )
        if lowered in self._confirm:
            return _decision(
                action, "tool", GateVerdict.CONFIRM, "tool-confirm-list",
                f"tool {name!r} requires confirmation", risk,
            )
        # Allowed = named in the allow-list, OR registered under a
        # wildcard allow-list (declared, not assumed).  A ghost tool —
        # neither registered nor named — escalates; it is never
        # silently allowed.
        named_explicitly = any(
            entry.lower() == lowered for entry in self._allowed
        )
        in_allowlist = named_explicitly or "*" in self._allowed
        registered = lowered in self._registry or lowered in self._risks
        if not (named_explicitly or (registered and in_allowlist)):
            return _decision(
                action, "tool", GateVerdict.CONFIRM, "tool-unregistered",
                f"tool {name!r} is not registered — escalated, never silent", risk,
            )
        return _decision(
            action, "tool", GateVerdict.ALLOW, "tool-allowed",
            f"tool {name!r} allowed (risk {risk.value})", risk,
        )

    def describe(self) -> dict[str, Any]:
        """Capability-matrix rows — declared facts only."""
        return {
            "gate": self.id,
            "blocked": sorted(self._blocked),
            "confirm": sorted(self._confirm),
            "registered": [e.name for e in self._registry.values()],
        }


# ------------------------------------------------------------------ §21.4


@dataclass(frozen=True, slots=True)
class McpServer:
    """One registered MCP server — name, risk, tool allow-list."""

    name: str
    risk: RiskLevel = RiskLevel.MEDIUM
    allowed_tools: tuple[str, ...] = ("*",)


class McpGate:
    """§21.4 — the MCP Gate (server registry + per-server tools)."""

    id = "mcp-gate"

    def __init__(
        self,
        *,
        allowed_servers: Iterable[str] = ("*",),
        blocked_servers: Iterable[str] = (),
    ) -> None:
        self._allowed = tuple(s.strip() for s in allowed_servers if s.strip())
        self._blocked = frozenset(s.strip().lower() for s in blocked_servers if s.strip())
        self._servers: dict[str, McpServer] = {}

    def register(
        self,
        server: str,
        *,
        tools: Iterable[str] = ("*",),
        risk: RiskLevel = RiskLevel.MEDIUM,
    ) -> McpServer:
        """Register an MCP server and its tool allow-list."""
        entry = McpServer(
            name=server.strip(),
            risk=risk,
            allowed_tools=tuple(t.strip() for t in tools if t.strip()) or ("*",),
        )
        self._servers[entry.name.lower()] = entry
        return entry

    def evaluate(self, action: SecurityAction) -> GateDecision:
        """One ``server:tool`` action → its gate decision."""
        if action.kind != "mcp":
            raise SecurityError(f"McpGate admits kind 'mcp', got {action.kind!r}")
        server, _, tool = action.name.partition(":")
        server, tool = server.strip(), tool.strip()
        lowered = server.lower()
        if not server or not tool:
            raise SecurityError(
                "mcp action.name must be 'server:tool' — got "
                f"{action.name!r}"
            )
        risk = _risk_of(action, {}, RiskLevel.MEDIUM)
        entry = self._servers.get(lowered)
        if entry is not None:
            risk = entry.risk
        if lowered in self._blocked:
            return _decision(
                action, "mcp", GateVerdict.DENY, "mcp-server-blocked",
                f"MCP server {server!r} is blocked", risk,
            )
        if entry is None:
            return _decision(
                action, "mcp", GateVerdict.CONFIRM, "mcp-server-unregistered",
                f"MCP server {server!r} is not registered — escalated", risk,
            )
        if not any(
            t == "*" or t.lower() == tool.lower() for t in entry.allowed_tools
        ):
            return _decision(
                action, "mcp", GateVerdict.CONFIRM, "mcp-tool-not-allowed",
                f"tool {tool!r} is outside server {server!r}'s allow-list", risk,
            )
        if not any(s == "*" or s.lower() == lowered for s in self._allowed):
            return _decision(
                action, "mcp", GateVerdict.CONFIRM, "mcp-server-not-allowed",
                f"server {server!r} is outside the allowed list", risk,
            )
        return _decision(
            action, "mcp", GateVerdict.ALLOW, "mcp-allowed",
            f"{server!r}:{tool!r} allowed (risk {risk.value})", risk,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "gate": self.id,
            "blocked_servers": sorted(self._blocked),
            "servers": [s.name for s in self._servers.values()],
        }


# ------------------------------------------------------------------ §21.5

#: The permissions a plugin may declare (§21.5) — ``secrets`` is the
#: one behind the §21.6 reference law, never a plugin default.
PLUGIN_PERMISSIONS: tuple[str, ...] = (
    "filesystem_read",
    "filesystem_write",
    "network",
    "process",
    "memory",
    "secrets",
)

#: Permissions that escalate unless the plugin is explicitly trusted.
_PLUGIN_HIGH: frozenset[str] = frozenset(
    {"filesystem_write", "network", "process"}
)


@dataclass(frozen=True, slots=True)
class PluginRegistration:
    """One registered plugin — its declared permissions and trust."""

    id: str
    permissions: tuple[str, ...] = ()
    trusted: bool = False
    secrets_granted: bool = False


class PluginGate:
    """§21.5 — the Plugin Gate (declared permissions, not assumed)."""

    id = "plugin-gate"

    def __init__(self, *, blocked: Iterable[str] = ()) -> None:
        self._blocked = frozenset(p.strip().lower() for p in blocked if p.strip())
        self._plugins: dict[str, PluginRegistration] = {}

    def register(
        self,
        plugin_id: str,
        *,
        permissions: Iterable[str] = (),
        trusted: bool = False,
        secrets_granted: bool = False,
    ) -> PluginRegistration:
        """Register a plugin with its *declared* permission set."""
        unknown = [
            p for p in permissions
            if p.strip() and p.strip() not in PLUGIN_PERMISSIONS
        ]
        if unknown:
            raise SecurityError(
                f"plugin {plugin_id!r} declares unknown permissions {unknown} — "
                f"allowed: {PLUGIN_PERMISSIONS}"
            )
        entry = PluginRegistration(
            id=plugin_id.strip(),
            permissions=tuple(p.strip() for p in permissions if p.strip()),
            trusted=trusted,
            secrets_granted=secrets_granted,
        )
        self._plugins[entry.id.lower()] = entry
        return entry

    def evaluate(self, action: SecurityAction) -> GateDecision:
        """One plugin action → its gate decision."""
        if action.kind != "plugin":
            raise SecurityError(f"PluginGate admits kind 'plugin', got {action.kind!r}")
        plugin_id = action.name.strip()
        lowered = plugin_id.lower()
        risk = _risk_of(action, {}, RiskLevel.MEDIUM)
        entry = self._plugins.get(lowered)
        if lowered in self._blocked:
            return _decision(
                action, "plugin", GateVerdict.DENY, "plugin-blocked",
                f"plugin {plugin_id!r} is blocked", risk,
            )
        if entry is None:
            return _decision(
                action, "plugin", GateVerdict.CONFIRM, "plugin-unregistered",
                f"plugin {plugin_id!r} is not registered — escalated", risk,
            )
        requested = action.target.strip() or (
            entry.permissions[0] if entry.permissions else ""
        )
        if requested == "secrets":
            if not entry.secrets_granted:
                return _decision(
                    action, "plugin", GateVerdict.DENY, "plugin-secrets-not-granted",
                    "secret access is never a plugin default — explicit grant "
                    "required (§21.6)",
                    RiskLevel.HIGH,
                )
            risk = RiskLevel.HIGH
        elif requested in _PLUGIN_HIGH:
            risk = RiskLevel.HIGH
            if not entry.trusted:
                return _decision(
                    action, "plugin", GateVerdict.CONFIRM, "plugin-high-permission",
                    f"permission {requested!r} needs a trusted plugin or a human",
                    risk,
                )
        return _decision(
            action, "plugin", GateVerdict.ALLOW, "plugin-allowed",
            f"plugin {plugin_id!r} allowed for {requested!r} "
            f"(risk {risk.value})", risk,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "gate": self.id,
            "blocked": sorted(self._blocked),
            "plugins": [
                {"id": p.id, "permissions": list(p.permissions), "trusted": p.trusted}
                for p in self._plugins.values()
            ],
        }


# ------------------------------------------------------ the pipeline (§57)


@dataclass(frozen=True, slots=True)
class AdmissionReport:
    """One admission walk — every stage's decision, in order."""

    stages: tuple[GateDecision, ...] = field(default_factory=tuple)
    final: GateDecision | None = None

    @property
    def allowed(self) -> bool:
        return self.final is not None and self.final.allowed

    def as_dict(self) -> dict[str, Any]:
        return {
            "stages": [d.as_dict() for d in self.stages],
            "final": self.final.as_dict() if self.final else None,
            "allowed": self.allowed,
        }


class GatePipeline:
    """The full admission walk (v0.1 §57, verbatim order)::

        Scope check → Permission check → Gate check → Audit
    """

    def __init__(
        self,
        *,
        permission: PermissionEngine | None = None,
        tool_gate: ToolGate | None = None,
        mcp_gate: McpGate | None = None,
        plugin_gate: PluginGate | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.permission = permission or PermissionEngine()
        self.tool_gate = tool_gate or ToolGate()
        self.mcp_gate = mcp_gate or McpGate()
        self.plugin_gate = plugin_gate or PluginGate()
        self.audit = audit

    def admit(
        self,
        action: SecurityAction,
        *,
        scope: Scope | None = None,
        policy: TaskPolicy | None = None,
        manager: WorkspaceManager | None = None,
    ) -> AdmissionReport:
        """Walk *action* through every stage — every verdict audited."""
        stages: list[GateDecision] = []

        first = self.permission.decide(action, scope=scope, policy=policy, manager=manager)
        stages.append(first)
        if first.verdict is GateVerdict.DENY:
            self._record(first)
            return AdmissionReport(stages=tuple(stages), final=first)

        gate = self._gate_for(action)
        if gate is not None:
            second = gate.evaluate(action)
            stages.append(second)
            self._record(second)
            return AdmissionReport(stages=tuple(stages), final=second)

        self._record(first)
        return AdmissionReport(stages=tuple(stages), final=first)

    def _gate_for(self, action: SecurityAction) -> ToolGate | McpGate | PluginGate | None:
        if action.kind == "tool":
            return self.tool_gate
        if action.kind == "mcp":
            return self.mcp_gate
        if action.kind == "plugin":
            return self.plugin_gate
        return None

    def _record(self, decision: GateDecision) -> None:
        if self.audit is None:
            return
        self.audit.record_decision(decision)


def make_pipeline(**kwargs: Any) -> GatePipeline:
    """The house pipeline (permission + three gates + audit)."""
    return GatePipeline(**kwargs)


__all__ = [
    "AdmissionReport",
    "GatePipeline",
    "GateVerdict",
    "McpGate",
    "McpServer",
    "PLUGIN_PERMISSIONS",
    "PluginGate",
    "PluginRegistration",
    "ToolGate",
    "ToolRegistration",
    "make_pipeline",
]
