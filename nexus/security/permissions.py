"""Scope Engine Integration + Permission Engine (New Plan §21.1–§21.2).

**§21.1 Scope Engine Integration** — the security pipeline does not
re-implement boundaries; it *consumes* the Phase 2 engine: the
§3.2/§3.3 resolved :class:`nexus.core.scope.engine.ScopeResolution`
is the first check of every admission, and cross-workspace requests
ride §3.4's audited carve (:class:`CrossWorkspaceAccess` is the only
bridge — histories never merge).

**§21.2 Permission Engine** — the Spec §163 risk classification
(``Read file = low · Edit file = medium · Delete file = high · Run
unrestricted command = high · Push release = high``) combined with
the §3.5 policy decision into one :class:`GateDecision`.  The
combination honours both laws at once:

* Blueprint §79 — security is not an obstacle: an explicit policy
  denial is the only denial; everything else flows or escalates.
* Spec §163's note — L4 (FULL autonomy) may execute even high-risk
  actions *when they sit within the task and its policy*; below FULL,
  high risk escalates to confirmation instead.

قرار الإذن = تصنيف الخطر §163 × قرار السياسة §3.5 × نطاق المهمة §3.2 —
وانكار صريح فقط هو المنع؛ الباقي يجري أو يُصعَّد.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.policy.engine import ActionType, PolicyAction, PolicyEngine
from ..core.policy.models import AutonomyLevel, TaskPolicy
from ..core.scope.engine import ScopeEngine, ScopeResolution
from ..core.scope.models import Scope
from ..core.workspace.manager import WorkspaceManager
from ..core.workspace.models import Workspace
from .contracts import GateDecision, GateVerdict, RiskLevel, SecurityAction, SecurityError

# ------------------------------------------------- §163 the risk ladder

#: Spec §163's classification examples, verbatim and in order —
#: the ladder the permission engine starts from.
RISK_CLASSIFICATION: tuple[tuple[str, str, RiskLevel], ...] = (
    ("read file", "read", RiskLevel.LOW),
    ("edit file", "write", RiskLevel.MEDIUM),
    ("delete file", "delete", RiskLevel.HIGH),
    ("run unrestricted command", "execute_unrestricted", RiskLevel.HIGH),
    ("push release", "push_release", RiskLevel.HIGH),
)


def classify(action: SecurityAction) -> RiskLevel:
    """The §163 risk of one action (an explicit ``risk_hint`` wins)."""
    if action.risk_hint is not None:
        return action.risk_hint
    kind, name = action.kind, action.name.strip().lower()
    if kind == "file":
        if name == "read":
            return RiskLevel.LOW
        if name in {"write", "edit", "create"}:
            return RiskLevel.MEDIUM
        if name in {"delete", "remove", "format"}:
            return RiskLevel.HIGH
    if kind == "command":
        return RiskLevel.HIGH  # run unrestricted command — §163
    if kind == "git":
        if name in {"push", "push_release", "release"}:
            return RiskLevel.HIGH  # push release — §163
        if name == "commit":
            return RiskLevel.MEDIUM
        if name == "pull":
            return RiskLevel.LOW
    if kind in {"tool", "mcp"}:
        return RiskLevel.MEDIUM
    if kind == "plugin":
        return RiskLevel.MEDIUM
    return RiskLevel.MEDIUM


# ------------------------------------------------------ §21.1 integration


@dataclass(frozen=True, slots=True)
class ScopeContext:
    """The §21.1 hand-off: a resolved scope bound to its resolution.

    ``workspace_id`` ties every downstream :class:`GateDecision` to
    the workspace the §3.3 resolution named (the decision's ``detail``
    carries it into the §21.8 audit).
    """

    resolution: ScopeResolution
    scope: Scope

    @property
    def workspace_id(self) -> str:
        return self.resolution.workspace.id

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "matched": self.resolution.matched,
            "confidence": self.resolution.confidence,
            "scope": self.scope.to_scope_map(),
        }


class ScopeEngineIntegration:
    """§21.1 — the security side of the Phase 2 scope engine."""

    def __init__(self, scope_engine: ScopeEngine | None = None) -> None:
        self._scope_engine = scope_engine

    def scope_for(
        self,
        request: str,
        *,
        manager: WorkspaceManager | None = None,
    ) -> ScopeContext:
        """Resolve a natural-language request (§3.3) into the context
        the permission engine consumes."""
        engine = self._scope_engine or ScopeEngine()
        resolution = engine.resolve(request, manager=manager)
        return ScopeContext(resolution=resolution, scope=resolution.scope)

    def cross_workspace(
        self,
        source: Workspace | str,
        target: Workspace | str,
        part: str,
        *,
        manager: WorkspaceManager | None = None,
    ) -> Any:
        """A §3.4 audited carve — the only bridge between histories."""
        engine = self._scope_engine or ScopeEngine()
        return engine.request_cross_workspace(source, target, part, manager=manager)


# ------------------------------------------------------ §21.2 the engine

_POLICY_KIND: dict[str, ActionType] = {
    "file": ActionType.WRITE,  # refined by name below
    "command": ActionType.EXECUTE,
    "tool": ActionType.TOOL,
    "network": ActionType.NETWORK,
    "git": ActionType.GIT_COMMIT,  # refined by name below
    "app": ActionType.APP_LAUNCH,
    "browser": ActionType.BROWSER_SESSION,
    "external_ai": ActionType.EXTERNAL_AI,
    "cross_workspace": ActionType.CROSS_WORKSPACE,
}


def _to_policy_action(action: SecurityAction) -> PolicyAction:
    """Map a :class:`SecurityAction` onto the §3.5 policy vocabulary."""
    kind, name = action.kind, action.name.strip().lower()
    action_type = _POLICY_KIND.get(kind)
    if action_type is None:
        # plugin / mcp ride the TOOL family for policy purposes (the
        # dedicated §21.4/§21.5 gates refine them afterwards).
        action_type = ActionType.TOOL
    if kind == "file":
        if name == "read":
            action_type = ActionType.READ
        elif name in {"write", "edit", "create"}:
            action_type = ActionType.WRITE
        elif name in {"delete", "remove", "format"}:
            action_type = ActionType.DELETE
        else:
            action_type = ActionType.EXECUTE
    if kind == "git":
        if name == "push":
            action_type = ActionType.GIT_PUSH
        elif name == "pull":
            action_type = ActionType.GIT_PULL
    # The policy engine speaks the *tool name* for TOOL-family actions
    # (§21.3–§21.5 refine the dedicated gates afterwards).
    policy_target = action.target
    if kind in {"tool", "mcp", "plugin"} and not policy_target:
        policy_target = action.name
    return PolicyAction(
        action_type=action_type,
        target=policy_target,
        detail=action.detail,
    )


class PermissionEngine:
    """§21.2 — §163 risk × §3.5 policy × §3.2 scope → one decision."""

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self._policy_engine = policy_engine or PolicyEngine()

    def decide(
        self,
        action: SecurityAction,
        *,
        scope: Scope | None = None,
        policy: TaskPolicy | None = None,
        manager: WorkspaceManager | None = None,
    ) -> GateDecision:
        """Admit or refuse *action* — the audit record is the decision."""
        risk = classify(action)
        task_policy = policy or TaskPolicy.default(task_id=action.task_id or None)
        decision = self._policy_engine.decide(
            _to_policy_action(action),
            task_policy,
            manager=manager,
            task_scope=scope,
        )
        verdict = GateVerdict(decision.verdict)
        rule = "policy"
        reason = decision.reason

        if verdict is GateVerdict.ALLOW and risk is RiskLevel.HIGH:
            if task_policy.autonomy_level is AutonomyLevel.FULL and decision.in_scope:
                # §163's note: L4 executes high risk inside task+policy.
                rule = "high-risk-in-scope-at-full-autonomy"
                reason = (
                    f"high risk ({risk.value}) executed inside the task and "
                    "its policy at FULL autonomy — audited"
                )
            else:
                verdict = GateVerdict.CONFIRM
                rule = "high-risk-requires-confirmation"
                reason = (
                    f"high risk ({risk.value}) outside FULL autonomy or "
                    "outside the task scope — confirmation required"
                )

        return GateDecision(
            action=action,
            verdict=verdict,
            risk=risk,
            gate="permission",
            rule=rule,
            reason=reason,
        )


def make_permission_engine() -> PermissionEngine:
    """The house permission engine (§21.2)."""
    return PermissionEngine()


__all__ = [
    "PermissionEngine",
    "RISK_CLASSIFICATION",
    "ScopeContext",
    "ScopeEngineIntegration",
    "SecurityAction",
    "SecurityError",
    "classify",
    "make_permission_engine",
]
