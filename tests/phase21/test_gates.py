"""Phase-21 gates tests — §21.3 Tool · §21.4 MCP · §21.5 Plugin · pipeline."""

from __future__ import annotations

import pytest

from nexus.core.policy.models import TaskPolicy
from nexus.security import (
    AuditLog,
    GatePipeline,
    GateVerdict,
    McpGate,
    PluginGate,
    RiskLevel,
    SecurityAction,
    SecurityError,
    ToolGate,
)


def test_tool_gate_blocked_denied() -> None:
    gate = ToolGate(blocked=["format-disk"])
    decision = gate.evaluate(SecurityAction(kind="tool", name="format-disk"))
    assert decision.verdict is GateVerdict.DENY
    assert decision.rule == "tool-blocked"


def test_tool_gate_confirm_first_and_list() -> None:
    gate = ToolGate()
    gate.register("release-publisher", risk=RiskLevel.HIGH, confirm_first=True)
    confirmed = gate.evaluate(SecurityAction(kind="tool", name="release-publisher"))
    assert confirmed.verdict is GateVerdict.CONFIRM
    assert confirmed.risk is RiskLevel.HIGH
    listed = ToolGate(confirm=["terminal"]).evaluate(
        SecurityAction(kind="tool", name="terminal")
    )
    assert listed.verdict is GateVerdict.CONFIRM


def test_tool_gate_unregistered_escalates_never_silent() -> None:
    gate = ToolGate(allowed=["editor"])
    decision = gate.evaluate(SecurityAction(kind="tool", name="unknown-tool"))
    assert decision.verdict is GateVerdict.CONFIRM
    assert "not registered" in decision.reason


def test_tool_gate_allows_registered() -> None:
    gate = ToolGate()
    gate.register("editor", risk=RiskLevel.LOW)
    decision = gate.evaluate(SecurityAction(kind="tool", name="editor"))
    assert decision.verdict is GateVerdict.ALLOW
    assert decision.gate == "tool"
    assert "low" in decision.reason


def test_tool_gate_rejects_foreign_kind() -> None:
    with pytest.raises(SecurityError):
        ToolGate().evaluate(SecurityAction(kind="mcp", name="a:b"))


def test_mcp_gate_server_blocked_and_unregistered() -> None:
    gate = McpGate(blocked_servers=["untrusted-mcp"])
    denied = gate.evaluate(SecurityAction(kind="mcp", name="untrusted-mcp:read_file"))
    assert denied.verdict is GateVerdict.DENY
    escalated = gate.evaluate(SecurityAction(kind="mcp", name="stranger:tool"))
    assert escalated.verdict is GateVerdict.CONFIRM


def test_mcp_gate_tool_allowlist_enforced() -> None:
    gate = McpGate()
    gate.register("filesystem", tools=["read_file", "list_dir"])
    allowed = gate.evaluate(SecurityAction(kind="mcp", name="filesystem:read_file"))
    assert allowed.verdict is GateVerdict.ALLOW
    outside = gate.evaluate(SecurityAction(kind="mcp", name="filesystem:delete_tree"))
    assert outside.verdict is GateVerdict.CONFIRM
    assert "allow-list" in outside.reason


def test_mcp_gate_requires_server_tool_shape() -> None:
    with pytest.raises(SecurityError):
        McpGate().evaluate(SecurityAction(kind="mcp", name="just-a-tool"))


def test_plugin_gate_secrets_never_a_default() -> None:
    """§21.6 — secret access is denied unless explicitly granted."""
    gate = PluginGate()
    gate.register("memory-helper", permissions=["memory"])
    denied = gate.evaluate(SecurityAction(kind="plugin", name="memory-helper", target="secrets"))
    assert denied.verdict is GateVerdict.DENY
    assert denied.risk is RiskLevel.HIGH
    gate.register("cred-reader", permissions=["secrets"], secrets_granted=True)
    granted = gate.evaluate(SecurityAction(kind="plugin", name="cred-reader", target="secrets"))
    assert granted.verdict is GateVerdict.ALLOW


def test_plugin_gate_high_permissions_need_trust() -> None:
    gate = PluginGate()
    gate.register("uploader", permissions=["network"])
    confirm = gate.evaluate(SecurityAction(kind="plugin", name="uploader", target="network"))
    assert confirm.verdict is GateVerdict.CONFIRM
    gate.register("trusted-uploader", permissions=["network"], trusted=True)
    allowed = gate.evaluate(
        SecurityAction(kind="plugin", name="trusted-uploader", target="network")
    )
    assert allowed.verdict is GateVerdict.ALLOW


def test_plugin_gate_unknown_declared_permissions_refused() -> None:
    with pytest.raises(SecurityError):
        PluginGate().register("rogue", permissions=["root_access"])


def test_plugin_gate_unregistered_escalates() -> None:
    decision = PluginGate().evaluate(SecurityAction(kind="plugin", name="ghost"))
    assert decision.verdict is GateVerdict.CONFIRM


def test_pipeline_full_walk_audits_every_verdict(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The v0.1 §57 order — scope → permission → gate → audit."""
    audit = AuditLog()
    tool_gate = ToolGate(blocked=["format-disk"])
    tool_gate.register("editor", risk=RiskLevel.LOW)
    pipeline = GatePipeline(tool_gate=tool_gate, audit=audit)
    denied = pipeline.admit(
        SecurityAction(kind="tool", name="format-disk", target="format-disk"),
        policy=TaskPolicy.default(),
    )
    assert not denied.allowed and denied.final is not None
    assert [d.gate for d in denied.stages] == ["permission", "tool"]
    allowed = pipeline.admit(
        SecurityAction(kind="tool", name="editor", target="editor"),
        policy=TaskPolicy.default(),
    )
    assert allowed.allowed
    assert audit.size() == 2
    verdicts = {r.result for r in audit.history()}
    assert verdicts == {"deny", "allow"}


def test_pipeline_denied_at_permission_skips_gate() -> None:
    pipeline = GatePipeline(tool_gate=ToolGate())
    report = pipeline.admit(
        SecurityAction(kind="tool", name="anything"),
        policy=TaskPolicy.from_overrides({"tool_policy.blocked_tools": ["anything"]}),
    )
    assert [d.gate for d in report.stages] == ["permission"]
    assert report.final is not None and report.final.verdict is GateVerdict.DENY


def test_pipeline_routes_mcp_and_plugin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    audit = AuditLog()
    mcp = McpGate()
    mcp.register("github-mcp", tools=["create_issue"])
    plugin = PluginGate()
    plugin.register("formatter", permissions=["filesystem_read"])
    pipeline = GatePipeline(mcp_gate=mcp, plugin_gate=plugin, audit=audit)
    mcp_ok = pipeline.admit(
        SecurityAction(kind="mcp", name="github-mcp:create_issue"), policy=TaskPolicy.default()
    )
    assert mcp_ok.allowed
    plugin_ok = pipeline.admit(
        SecurityAction(kind="plugin", name="formatter", target="filesystem_read"),
        policy=TaskPolicy.default(),
    )
    assert plugin_ok.allowed
    assert audit.size() == 2
