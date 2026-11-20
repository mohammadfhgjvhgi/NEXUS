"""§22 contracts — the verbatim vocabulary and the manifest round-trip."""

from __future__ import annotations

import dataclasses

import pytest

from nexus.recovery import (
    CHECKPOINT_SCOPES,
    RECOVERY_CHAIN,
    RECOVERY_SCHEMA_VERSION,
    TRIGGER_EVENTS,
    VERIFICATION_SURFACES,
    CheckpointManifest,
    CheckpointNotFoundError,
    CheckpointScope,
    CorruptCheckpointError,
    Drift,
    DriftKind,
    DriftSeverity,
    EnvironmentFacts,
    FileEntry,
    NoBlindResumeError,
    ReconciliationReport,
    RecoveryAction,
    RecoveryError,
    RecoveryOutcome,
    RecoveryVerdict,
    TriggerEvent,
    VerificationSurface,
)


def test_vocabulary_verbatim() -> None:
    """§22.1/§22.2/§22.4 tuples — exactly the plan's words, in order."""
    assert CHECKPOINT_SCOPES == ("task", "project", "git", "state")
    assert TRIGGER_EVENTS == (
        "task_start",
        "phase_complete",
        "major_change",
        "critical_test",
        "before_risky_change",
        "periodic",
    )
    assert VERIFICATION_SURFACES == (
        "files",
        "git",
        "processes",
        "windows",
        "browser",
        "task_state",
    )


def test_recovery_chain_verbatim() -> None:
    """§22.3 chain — Crash → Checkpoint → Actual environment →
    Reconciliation → Resume, five stages in the plan's order."""
    assert RECOVERY_CHAIN == (
        "crash",
        "checkpoint",
        "actual_environment",
        "reconciliation",
        "resume",
    )


def test_enum_twins_match_the_tuples() -> None:
    assert {s.value for s in CheckpointScope} == set(CHECKPOINT_SCOPES)
    assert {e.value for e in TriggerEvent} == set(TRIGGER_EVENTS)
    assert {s.value for s in VerificationSurface} == set(VERIFICATION_SURFACES)
    assert {v.value for v in RecoveryVerdict} == {
        "resume_ready",
        "drift_detected",
        "unrecoverable",
    }
    assert {a.value for a in RecoveryAction} == {"resume", "restart_task", "abort"}


def test_schema_version_is_one() -> None:
    assert RECOVERY_SCHEMA_VERSION == 1


def test_manifest_roundtrip_with_unicode_state() -> None:
    manifest = CheckpointManifest(
        checkpoint_id="ck_task_20260212T101500Z_ab12",
        scope=CheckpointScope.TASK,
        trigger=TriggerEvent.TASK_START,
        label="before risky change",
        created_at_utc="2026-02-12T10:15:00+00:00",
        nexus_version="0.22.0",
        nexus_phase=22,
        git_head="a" * 40,
        git_branch="main",
        files=(FileEntry(path="src/app.py", sha256="b" * 64, size=12),),
        state={"task_state": {"الاسم": "مهمة", "steps": [1, 2, 3]}},
    )
    restored = CheckpointManifest.from_dict(manifest.to_dict())
    assert restored == manifest
    assert restored.state["task_state"]["الاسم"] == "مهمة"


def test_manifest_is_frozen() -> None:
    manifest = CheckpointManifest(
        checkpoint_id="ck_state_20260212T101500Z_cd34",
        scope=CheckpointScope.STATE,
        trigger=TriggerEvent.PERIODIC,
        label="",
        created_at_utc="2026-02-12T10:15:00+00:00",
        nexus_version="0.22.0",
        nexus_phase=22,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.label = "nope"  # type: ignore[misc]


def test_bad_manifest_refused() -> None:
    with pytest.raises(CorruptCheckpointError):
        CheckpointManifest.from_dict({"scope": "task"})  # no id/trigger
    with pytest.raises(CorruptCheckpointError):
        CheckpointManifest.from_dict(
            {
                "checkpoint_id": "ck_task_20260212T101500Z_ab12",
                "scope": "task",
                "trigger": "task_start",
                "created_at_utc": "x",
                "schema_version": 99,
            }
        )


def test_error_hierarchy() -> None:
    assert issubclass(CheckpointNotFoundError, RecoveryError)
    assert issubclass(CorruptCheckpointError, RecoveryError)
    assert issubclass(NoBlindResumeError, RecoveryError)


def test_drift_and_report_shapes() -> None:
    drift = Drift(
        surface=VerificationSurface.FILES,
        kind=DriftKind.FILE_MODIFIED,
        severity=DriftSeverity.ERROR,
        detail="content changed since capture: app.py",
    )
    assert drift.as_dict()["kind"] == "file_modified"
    report = ReconciliationReport(
        checkpoint_id="ck_project_20260212T101500Z_ef56",
        verdict=RecoveryVerdict.DRIFT_DETECTED,
        drift=(drift,),
    )
    assert not report.ok()
    assert report.errors()[0].kind is DriftKind.FILE_MODIFIED
    encoded = report.as_dict()
    assert encoded["drift"][0]["surface"] == "files"


def test_environment_facts_surface_accessor() -> None:
    facts = EnvironmentFacts(
        files={"a.txt": "x"},
        processes=("python",),
        windows=("Editor — main.py",),
        browser=("chrome",),
        task_state={"step": 2},
    )
    assert facts.surface(VerificationSurface.FILES) == {"a.txt": "x"}
    assert facts.surface(VerificationSurface.PROCESSES) == ("python",)
    assert facts.surface(VerificationSurface.TASK_STATE) == {"step": 2}
    assert facts.probed_at_utc  # stamped at construction


def test_outcome_stages_stop_before_resume() -> None:
    report = ReconciliationReport(
        checkpoint_id="ck",
        verdict=RecoveryVerdict.DRIFT_DETECTED,
    )
    outcome = RecoveryOutcome(
        checkpoint_id="ck",
        report=report,
        action=RecoveryAction.RESTART_TASK,
    )
    assert outcome.stages == ("crash", "checkpoint", "actual_environment", "reconciliation")

    ok_report = ReconciliationReport(
        checkpoint_id="ck", verdict=RecoveryVerdict.RESUME_READY
    )
    resumed = RecoveryOutcome(
        checkpoint_id="ck", report=ok_report, action=RecoveryAction.RESUME
    )
    assert resumed.stages == RECOVERY_CHAIN
    assert resumed.as_dict()["stages"] == list(RECOVERY_CHAIN)
