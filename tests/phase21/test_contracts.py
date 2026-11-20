"""Phase-21 contracts tests — §21 vocabulary, actions, decisions, credentials."""

from __future__ import annotations

import dataclasses

import pytest

from nexus.security import (
    ACTION_KINDS,
    CREDENTIAL_FIELDS,
    PROTECTED_SINKS,
    SCAN_KINDS,
    TRIVY_REPOSITORY,
    Credential,
    GateDecision,
    GateVerdict,
    PermissionDeniedError,
    RiskLevel,
    SecretError,
    SecretLeakError,
    SecurityAction,
    SecurityError,
    TrivyUnavailable,
)


def test_protected_sinks_verbatim() -> None:
    """§21.10 — the four sinks, verbatim and in order."""
    assert PROTECTED_SINKS == ("memory", "normal_chat", "logs", "activity")


def test_scan_kinds_verbatim() -> None:
    """§21.9 — the four scan kinds, verbatim and in order."""
    assert SCAN_KINDS == ("dependency", "secret", "license", "vulnerability")
    assert TRIVY_REPOSITORY == "aquasecurity/trivy"


def test_risk_levels_verbatim() -> None:
    """§163 — three levels, verbatim."""
    assert {level.value for level in RiskLevel} == {"low", "medium", "high"}


def test_gate_verdicts_align_with_policy() -> None:
    """The gate speaks the policy engine's three words."""
    assert {v.value for v in GateVerdict} == {"allow", "confirm", "deny"}


def test_action_kinds_cover_the_gates() -> None:
    assert ACTION_KINDS == (
        "file", "command", "tool", "mcp", "plugin", "network",
        "git", "app", "browser", "external_ai", "cross_workspace",
    )


def test_security_action_laws() -> None:
    action = SecurityAction(kind="file", name="delete", target="M:/x/a.txt")
    assert action.actor == "agent" and action.task_id == ""
    assert action.as_dict()["kind"] == "file"
    with pytest.raises(SecurityError):
        SecurityAction(kind="magic", name="x")
    with pytest.raises(SecurityError):
        SecurityAction(kind="file", name="")


def test_gate_decision_laws() -> None:
    action = SecurityAction(kind="tool", name="terminal")
    decision = GateDecision(
        action=action,
        verdict=GateVerdict.ALLOW,
        risk=RiskLevel.MEDIUM,
        gate="tool",
        rule="tool-allowed",
        reason="ok",
    )
    assert decision.allowed and not decision.requires_confirmation
    assert decision.as_dict()["verdict"] == "allow"
    assert decision.as_dict()["gate"] == "tool"
    confirm = GateDecision(
        action=action, verdict=GateVerdict.CONFIRM, risk=RiskLevel.HIGH,
        gate="permission", rule="r",
    )
    assert confirm.allowed and confirm.requires_confirmation
    deny = GateDecision(
        action=action, verdict=GateVerdict.DENY, risk=RiskLevel.HIGH,
        gate="permission", rule="r",
    )
    assert not deny.allowed


def test_credential_six_fields_verbatim() -> None:
    """Spec §160 — ID | Provider | Scope | Reference | Created | last-used."""
    names = [f.name for f in dataclasses.fields(Credential)]
    assert tuple(names) == CREDENTIAL_FIELDS
    credential = Credential(id="sec_x", provider="github", scope="task", reference="vault://github/sec_x")
    assert set(credential.as_dict()) == set(CREDENTIAL_FIELDS)


def test_credential_never_carries_text() -> None:
    """The reference law — a credential's surface has no secret text."""
    credential = Credential(id="sec_x", provider="github", scope="task", reference="vault://github/sec_x")
    rendered = repr(credential) + str(credential.as_dict())
    assert "hunter2" not in rendered  # the text simply is not a field


def test_error_family() -> None:
    assert issubclass(SecretError, SecurityError)
    assert issubclass(SecretLeakError, SecurityError)
    assert issubclass(TrivyUnavailable, SecurityError)
    assert issubclass(PermissionDeniedError, SecurityError)
