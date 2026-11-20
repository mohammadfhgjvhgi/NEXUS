"""Phase 23 contracts — the §23 vocabulary is verbatim or it is wrong."""

from __future__ import annotations

import pytest

from nexus.health import (
    HEALTH_SCHEMA_VERSION,
    MONITORED_COMPONENTS,
    RECOVERY_LADDER,
    STALL_SIGNALS,
    ComponentStatus,
    Diagnosis,
    HealthError,
    HealthReport,
    HealthVerdict,
    Heartbeat,
    LadderOutcome,
    MonitoredComponent,
    Observation,
    RecoveryResolution,
    StallFinding,
    StallSignal,
    SupervisorReport,
    UnknownComponentError,
)


def test_section_vocabulary_verbatim() -> None:
    """§23.1 seven components · §23.2 four signals · §23.3 five rungs."""
    assert MONITORED_COMPONENTS == (
        "core", "agent", "model", "tool", "browser", "computer", "task",
    )
    assert STALL_SIGNALS == (
        "same_action", "same_error", "same_state", "no_progress",
    )
    assert RECOVERY_LADDER == (
        "detect", "diagnose", "retry", "alternate_method", "replan",
    )
    assert {c.value for c in MonitoredComponent} == set(MONITORED_COMPONENTS)
    assert {s.value for s in StallSignal} == set(STALL_SIGNALS)
    assert {v.value for v in HealthVerdict} == {"healthy", "degraded", "stalled"}
    assert {r.value for r in RecoveryResolution} == {
        "not_confirmed", "resolved", "replan_needed",
    }
    assert {c.value for c in ComponentStatus} == {
        "alive", "degraded", "stalled", "silent",
    }
    assert HEALTH_SCHEMA_VERSION == 1


def test_error_family() -> None:
    assert issubclass(UnknownComponentError, HealthError)
    with pytest.raises(HealthError):
        raise UnknownComponentError("§23.1")


def test_heartbeat_roundtrip() -> None:
    hb = Heartbeat(
        component=MonitoredComponent.COMPUTER,
        status=ComponentStatus.DEGRADED,
        seq=7,
        age_seconds=41.5,
        detail="beats are late",
        last_beat_utc="2026-09-10T03:00:00+00:00",
        checked_at_utc="2026-09-10T03:00:41+00:00",
    )
    assert Heartbeat.from_dict(hb.as_dict()) == hb
    never = Heartbeat(
        component=MonitoredComponent.MODEL,
        status=ComponentStatus.SILENT,
        seq=0,
        age_seconds=None,
    )
    restored = Heartbeat.from_dict(never.as_dict())
    assert restored.age_seconds is None and restored.status is ComponentStatus.SILENT


def test_health_report_roundtrip_and_lookup() -> None:
    report = HealthReport(
        verdict=HealthVerdict.STALLED,
        components=(
            Heartbeat(
                component=MonitoredComponent.TASK,
                status=ComponentStatus.STALLED,
                seq=3,
                age_seconds=1.0,
            ),
        ),
    )
    assert HealthReport.from_dict(report.as_dict()) == report
    assert report.component("task") is not None
    assert report.component("core") is None
    assert report.component(MonitoredComponent.TASK) is not None


def test_observation_roundtrip_defaults() -> None:
    obs = Observation(action="click", error="", state="h1", progress="p1")
    assert Observation.from_dict(obs.as_dict()) == obs
    empty = Observation()
    assert empty.action == "" and empty.state == ""


def test_stall_finding_roundtrip_component_optional() -> None:
    finding = StallFinding(
        signal=StallSignal.SAME_ERROR,
        repeats=4,
        detail="error 'timeout' repeated 4×",
        component=MonitoredComponent.TOOL,
    )
    assert StallFinding.from_dict(finding.as_dict()) == finding
    bare = StallFinding(signal=StallSignal.NO_PROGRESS, repeats=0, detail="silent")
    restored = StallFinding.from_dict(bare.as_dict())
    assert restored.component is None


def test_diagnosis_roundtrip() -> None:
    d = Diagnosis(signal=StallSignal.SAME_STATE, cause="frozen", confidence=0.9)
    assert Diagnosis.from_dict(d.as_dict()) == d


def _finding() -> StallFinding:
    return StallFinding(
        signal=StallSignal.SAME_ACTION, repeats=3, detail="loop"
    )


def test_ladder_outcome_stages_are_the_verbatim_prefix() -> None:
    outcome = LadderOutcome(
        finding=_finding(),
        resolution=RecoveryResolution.RESOLVED,
        rungs=("detect", "diagnose", "retry"),
        stopped_at="retry",
        detail="retry: resolved",
    )
    assert outcome.stages == ("detect", "diagnose", "retry")
    full = LadderOutcome(
        finding=_finding(),
        resolution=RecoveryResolution.REPLAN_NEEDED,
        rungs=RECOVERY_LADDER,
        stopped_at="replan",
    )
    assert full.stages == RECOVERY_LADDER


def test_ladder_outcome_roundtrip_with_diagnosis() -> None:
    outcome = LadderOutcome(
        finding=_finding(),
        resolution=RecoveryResolution.REPLAN_NEEDED,
        rungs=RECOVERY_LADDER,
        stopped_at="replan",
        detail="climbed the whole ladder",
        diagnosis=Diagnosis(signal=StallSignal.SAME_ACTION, cause="loop", confidence=0.5),
    )
    assert LadderOutcome.from_dict(outcome.as_dict()) == outcome


def test_supervisor_report_roundtrip() -> None:
    report = SupervisorReport(
        health=HealthReport(verdict=HealthVerdict.HEALTHY),
        findings=(_finding(),),
        outcomes=(
            LadderOutcome(
                finding=_finding(),
                resolution=RecoveryResolution.RESOLVED,
                rungs=("detect", "diagnose", "retry"),
                stopped_at="retry",
            ),
        ),
    )
    assert SupervisorReport.from_dict(report.as_dict()) == report
