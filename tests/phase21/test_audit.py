"""Phase-21 audit tests — §21.8 five fields, JSONL, guards, Activity split."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.security import (
    AUDIT_FIELDS,
    ActivityFeed,
    AuditLog,
    AuditRecord,
    GateDecision,
    GateVerdict,
    RiskLevel,
    SecurityAction,
    make_audit_log,
)

# built by concatenation — no secret-shaped literal in this file
PLANT_TOKEN = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyzABCD"


def test_audit_fields_verbatim() -> None:
    """Spec §164 — Who | What | When | Where | Result."""
    assert AUDIT_FIELDS == ("who", "what", "when", "where", "result")
    record = AuditRecord(who="agent", what="file:delete", where="M:/x/a.txt", result="deny")
    assert tuple(record.as_dict())[:5] == AUDIT_FIELDS


def test_record_requires_who_and_what() -> None:
    with pytest.raises(ValueError):
        AuditRecord(who="", what="x", where="y", result="deny")
    with pytest.raises(ValueError):
        AuditRecord(who="agent", what="", where="y", result="deny")


def test_decision_maps_to_audit_record() -> None:
    decision = GateDecision(
        action=SecurityAction(kind="tool", name="terminal", target="terminal", actor="coder"),
        verdict=GateVerdict.CONFIRM,
        risk=RiskLevel.HIGH,
        gate="permission",
        rule="high-risk-requires-confirmation",
        reason="escalated",
    )
    record = AuditRecord.from_decision(decision)
    assert record.who == "coder"
    assert "tool:terminal" in record.what
    assert record.where == "terminal"
    assert record.result == "confirm"
    assert "gate=permission" in record.detail


def test_filter_by_who_what_result() -> None:
    log = make_audit_log()
    log.append(AuditRecord(who="agent", what="file:read", where="a", result="allow"))
    log.append(AuditRecord(who="agent", what="tool:terminal", where="b", result="confirm"))
    log.append(AuditRecord(who="human", what="file:delete", where="c", result="deny"))
    assert log.size() == 3
    assert len(log.filter(who="agent")) == 2
    assert len(log.filter(result="deny")) == 1
    assert len(log.filter(what_contains="terminal")) == 1
    assert len(log) == 3


def test_jsonl_roundtrip(tmp_path: Path) -> None:
    log = make_audit_log()
    log.append(AuditRecord(who="agent", what="git:push", where="develop", result="confirm"))
    target = log.write_jsonl(tmp_path / "audit" / "audit.jsonl")
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    doc = json.loads(lines[0])
    assert tuple(doc)[:5] == AUDIT_FIELDS
    assert doc["result"] == "confirm"


def test_guard_runs_at_append_not_by_discipline(tmp_path: Path) -> None:
    """§21.10 structural: the planted token never lands in the file."""
    from nexus.security import make_redactor

    guard = make_redactor().redact_to_safe
    log = AuditLog(guard=guard)
    log.append(
        AuditRecord(
            who="agent",
            what=f"tool:leaky token={PLANT_TOKEN}",
            where="nowhere",
            result="allow",
        )
    )
    target = log.write_jsonl(tmp_path / "guarded.jsonl")
    on_disk = target.read_text(encoding="utf-8")
    assert PLANT_TOKEN not in on_disk
    assert "[REDACTED:github_token]" in on_disk


def test_activity_feed_is_a_separate_surface() -> None:
    """Spec §165 — Activity (friendly) ≠ Audit (technical)."""
    from nexus.security import make_redactor

    guard = make_redactor().redact_to_safe
    audit = AuditLog(guard=guard)
    activity = ActivityFeed(guard=guard)
    audit.append(AuditRecord(who="agent", what="file:delete", where="a", result="confirm"))
    posted = activity.post("Cleaned up 3 temporary files ✓")
    assert len(audit) == 1 and len(activity) == 1
    assert activity.items() == (posted,)
    assert isinstance(audit.history()[0], AuditRecord)
    # the feed also guards: planted token never surfaces
    activity.post(f"token {PLANT_TOKEN} rotated")
    assert PLANT_TOKEN not in str(activity.items())
