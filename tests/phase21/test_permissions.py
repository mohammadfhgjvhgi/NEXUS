"""Phase-21 permission-engine tests — §21.1 integration + §21.2 decisions."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.core.policy.models import AutonomyLevel, TaskPolicy
from nexus.core.scope.engine import ScopeEngine
from nexus.core.scope.models import Scope
from nexus.core.workspace.manager import WorkspaceManager
from nexus.security import (
    RISK_CLASSIFICATION,
    GateVerdict,
    PermissionEngine,
    RiskLevel,
    ScopeEngineIntegration,
    SecurityAction,
    classify,
)

SECRET = "nexus-super-secret-text-7f3a9"  # kept for future fixture growth


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceManager:
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.register(
        name="ClientWebsite",
        path=str(tmp_path / "client"),
        project="website",
        settings={"tools": ["terminal", "editor"], "applications": ["vscode"]},
    )
    (tmp_path / "client").mkdir(exist_ok=True)
    (tmp_path / "client" / "auth.py").write_text("x = 1\n", encoding="utf-8")
    return manager


def test_risk_classification_examples_verbatim() -> None:
    """Spec §163 — the five examples, verbatim and in order."""
    assert RISK_CLASSIFICATION == (
        ("read file", "read", RiskLevel.LOW),
        ("edit file", "write", RiskLevel.MEDIUM),
        ("delete file", "delete", RiskLevel.HIGH),
        ("run unrestricted command", "execute_unrestricted", RiskLevel.HIGH),
        ("push release", "push_release", RiskLevel.HIGH),
    )


def test_classify_maps_the_ladder() -> None:
    assert classify(SecurityAction(kind="file", name="read", target="a.txt")) == RiskLevel.LOW
    assert classify(SecurityAction(kind="file", name="edit", target="a.txt")) == RiskLevel.MEDIUM
    assert classify(SecurityAction(kind="file", name="delete", target="a.txt")) == RiskLevel.HIGH
    assert classify(SecurityAction(kind="command", name="rm -rf /")) == RiskLevel.HIGH
    assert classify(SecurityAction(kind="git", name="push", target="main")) == RiskLevel.HIGH
    hint = SecurityAction(kind="file", name="read", target="a.txt", risk_hint=RiskLevel.HIGH)
    assert classify(hint) == RiskLevel.HIGH


def test_in_scope_read_allowed_at_full(workspace: WorkspaceManager) -> None:
    engine = PermissionEngine()
    integration = ScopeEngineIntegration(ScopeEngine())
    context = integration.scope_for("M:\\tmp\\client\\auth.py", manager=workspace)
    action = SecurityAction(kind="file", name="read", target="M:\\tmp\\client\\auth.py")
    decision = engine.decide(action, scope=context.scope)
    assert decision.verdict is GateVerdict.ALLOW
    assert decision.gate == "permission"
    assert decision.risk.value == "low"


def test_high_risk_in_scope_at_full_autonomy_executes(workspace: WorkspaceManager) -> None:
    """§163's note — L4 executes delete inside the task and its policy."""
    engine = PermissionEngine()
    integration = ScopeEngineIntegration(ScopeEngine())
    target_file = Path(workspace.list_workspaces()[0].path) / "auth.py"
    context = integration.scope_for(str(target_file), manager=workspace)
    action = SecurityAction(kind="file", name="delete", target=str(target_file))
    decision = engine.decide(action, scope=context.scope)
    assert decision.verdict is GateVerdict.ALLOW
    assert decision.rule == "high-risk-in-scope-at-full-autonomy"
    assert "audited" in decision.reason


def test_destructive_delete_confirms_by_policy(workspace: WorkspaceManager) -> None:
    """Below FULL autonomy the policy escalates DELETE before the risk rule."""
    engine = PermissionEngine()
    policy = TaskPolicy.default()
    policy.autonomy_level = AutonomyLevel.ACT_CONFIRMED
    target_file = Path(workspace.list_workspaces()[0].path) / "auth.py"
    action = SecurityAction(kind="file", name="delete", target=str(target_file))
    decision = engine.decide(action, policy=policy)
    assert decision.verdict is GateVerdict.CONFIRM
    assert "confirmation" in decision.reason


def test_high_risk_below_full_confirms() -> None:
    """§21.2 — high risk below FULL autonomy escalates (git push)."""
    engine = PermissionEngine()
    policy = TaskPolicy.default()
    policy.autonomy_level = AutonomyLevel.ACT_CONFIRMED
    action = SecurityAction(kind="git", name="push", target="feature-branch")
    decision = engine.decide(action, policy=policy, scope=Scope.empty())
    assert decision.verdict is GateVerdict.CONFIRM
    assert decision.rule == "high-risk-requires-confirmation"


def test_blocked_tool_denied_by_explicit_policy() -> None:
    """Blueprint §79 — explicit denial is the only hard stop."""
    engine = PermissionEngine()
    policy = TaskPolicy.from_overrides({"tool_policy.blocked_tools": ["format"]})
    action = SecurityAction(kind="tool", name="format", target="format")
    decision = engine.decide(action, policy=policy)
    assert decision.verdict is GateVerdict.DENY
    assert "blocked" in decision.reason


def test_observe_autonomy_refuses_mutations() -> None:
    engine = PermissionEngine()
    policy = TaskPolicy.from_overrides({"autonomy_level": "OBSERVE"})
    action = SecurityAction(kind="file", name="edit", target="M:\\tmp\\x.txt")
    decision = engine.decide(action, policy=policy)
    assert decision.verdict is GateVerdict.DENY
    assert "OBSERVE" in decision.reason


def test_out_of_scope_mutation_escalates(workspace: WorkspaceManager) -> None:
    engine = PermissionEngine()
    policy = TaskPolicy.default()
    policy.autonomy_level = AutonomyLevel.SUGGEST
    action = SecurityAction(kind="file", name="edit", target="C:\\elsewhere\\x.txt")
    decision = engine.decide(action, policy=policy, manager=workspace)
    assert decision.verdict is GateVerdict.CONFIRM
    assert "confirmation" in decision.reason


def test_out_of_scope_at_full_is_flagged_not_walled(workspace: WorkspaceManager) -> None:
    """§3.4 through §21.2 — FULL autonomy: allowed, flagged, never walled."""
    engine = PermissionEngine()
    action = SecurityAction(kind="file", name="edit", target="C:\\elsewhere\\x.txt")
    decision = engine.decide(action, policy=TaskPolicy.default(), manager=workspace)
    assert decision.verdict is GateVerdict.ALLOW
    assert "flagged" in decision.reason


def test_scope_integration_records_workspace(workspace: WorkspaceManager) -> None:
    """§21.1 — the resolved §3.3 scope rides into the decision context."""
    integration = ScopeEngineIntegration(ScopeEngine())
    context = integration.scope_for("the ClientWebsite auth", manager=workspace)
    assert context.workspace_id == workspace.list_workspaces()[0].id
    assert context.resolution.matched == "name"
    assert context.resolution.confidence == 0.8
    snapshot = context.as_dict()
    assert snapshot["matched"] == "name"


def test_cross_workspace_carve_is_audited(workspace: WorkspaceManager) -> None:
    """§3.4 through §21.1 — the carve is the only bridge, and audited."""
    integration = ScopeEngineIntegration(ScopeEngine())
    source = workspace.list_workspaces()[0]
    access = integration.cross_workspace(
        source, "ClientWebsite", "authentication", manager=workspace
    )
    assert access.granted
    assert access.requested_part == "authentication"
    assert len(integration._scope_engine.access_history()) == 1  # type: ignore[union-attr]


def test_git_push_high_risk_in_scope_full_allows_with_note() -> None:
    engine = PermissionEngine()
    action = SecurityAction(kind="git", name="push", target="develop")
    decision = engine.decide(action, scope=None, policy=TaskPolicy.default())
    # outside any scope at FULL autonomy → the policy allows (flagged);
    # the high-risk rule must not downgrade it below allow
    assert decision.verdict is GateVerdict.ALLOW
