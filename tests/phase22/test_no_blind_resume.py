"""§22.4 — No Blind Resume: each of the six surfaces alone blocks it.

The law, verbatim: «لا يعتمد على الذاكرة. يفحص: Files · Git ·
Processes · Windows · Browser · Task state» — so every one of the six
surfaces, drifting *alone*, must flip the verdict to
``drift_detected`` and make any resume demand raise
:class:`NoBlindResumeError`.  A resume after *repair* is legitimate —
it is still a verified resume (reconciled again, from a live probe).
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.recovery import (
    CheckpointManager,
    CheckpointScope,
    CompositeProbe,
    DiskCheckpointStore,
    Drift,
    DriftKind,
    DriftSeverity,
    NoBlindResumeError,
    ProcessProbe,
    ReconciliationReport,
    RecoveryAction,
    RecoveryVerdict,
    TriggerEvent,
    TriggerPolicy,
    VerificationSurface,
    WindowProbe,
)
from nexus.recovery.engine import RecoveryEngine

TASK_STATE = {"task": "T-22", "state": "RUNNING", "مرحلة": 4}

# (surface, captured-environment override, live-facts override)
SIX_CASES = [
    ("files", None, None),
    ("git", None, None),
    ("processes", {"processes": ["companion"]}, {"processes": ()}),
    ("windows", {"windows": ["Build output"]}, {"windows": ()}),
    ("browser", {"browser": ["chrome"]}, {"browser": ()}),
    ("task_state", None, None),
]


class _OverridableProbe:
    """The real probe, wrapped — one surface may be overridden to
    simulate exactly one machine change."""

    def __init__(self, base: CompositeProbe) -> None:
        self._base = base
        self.override: dict = {}

    def probe(self):  # noqa: ANN202
        facts = self._base.probe()
        return dataclasses.replace(facts, **self.override) if self.override else facts


@pytest.fixture()
def world(tmp_path: Path, repo: Path):
    store = DiskCheckpointStore(tmp_path / "checkpoints")
    manager = CheckpointManager(
        store, repo, version="0.22.0", phase=22,
        triggers=TriggerPolicy(min_interval_seconds=0),
        expectations_provider=lambda: ((), (), ()),
    )
    state_path = tmp_path / "task_state.json"
    state_path.write_text(json.dumps(TASK_STATE), encoding="utf-8")
    base = CompositeProbe(
        repo, state_path,
        processes=ProcessProbe(runner=lambda argv: ""),
        windows=WindowProbe(runner=lambda argv: ""),
    )
    engine = RecoveryEngine(store, repo, state_path, probe=_OverridableProbe(base))
    return repo, manager, engine, state_path


def _git_commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@n.dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "n"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", message], check=True)


def _capture(
    world, surface: str, env: dict | None, facts: dict | None
):  # noqa: ANN202
    """Capture a checkpoint, then bend exactly one surface of the world."""
    repo, manager, engine, state_path = world
    if surface == "git":
        _git_commit_all(repo, "captured head")
    extra = {"environment": {"processes": [], "windows": [], "browser": []} | (env or {})}
    manifest = manager.create(
        CheckpointScope.PROJECT,
        TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state=dict(TASK_STATE),
        extra_state=extra,
    )
    if surface == "files":
        (repo / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    elif surface == "git":
        if shutil.which("git") is None:  # pragma: no cover
            pytest.skip("git binary unavailable on this host")
        (repo / "later.txt").write_text("newer commit\n", encoding="utf-8")
        _git_commit_all(repo, "diverged")
    elif surface == "task_state":
        state_path.write_text(
            json.dumps({"task": "T-22", "state": "CRASHED"}), encoding="utf-8"
        )
    if facts:
        engine._probe.override = dict(facts)
    return manifest


@pytest.mark.parametrize("surface,env,facts", SIX_CASES)
def test_one_surface_alone_blocks_the_blind_resume(
    surface: str, env: dict | None, facts: dict | None, world
) -> None:
    repo, manager, engine, _ = world
    manifest = _capture(world, surface, env, facts)

    report = engine.reconcile(manifest)
    assert not report.ok(), f"{surface} did not block: {report.as_dict()}"
    assert report.verdict is RecoveryVerdict.DRIFT_DETECTED
    assert surface in {d.surface.value for d in report.errors()}

    # no repair → the outcome must never say resume
    outcome = engine.recover(manifest.checkpoint_id, repair=False)
    assert outcome.action is not RecoveryAction.RESUME
    assert outcome.action is RecoveryAction.RESTART_TASK


def test_resume_raises_on_drift(world) -> None:
    repo, _, engine, _ = world
    extra = {"environment": {"processes": [], "windows": [], "browser": []}}
    manifest = manager_create(world, extra)
    (repo / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    report = engine.reconcile(manifest)
    assert not report.ok()
    with pytest.raises(NoBlindResumeError) as excinfo:
        engine.resume(report)
    assert "no blind resume" in str(excinfo.value).lower()
    assert "files" in str(excinfo.value).lower()


def manager_create(world, extra: dict | None):  # noqa: ANN201, ANN001
    repo, manager, _, _ = world
    return manager.create(
        CheckpointScope.PROJECT,
        TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state=dict(TASK_STATE),
        extra_state={"environment": {"processes": [], "windows": [], "browser": []}}
        | (extra or {}),
    )


def test_resume_on_a_clean_report_is_the_only_door(world) -> None:
    _, _, engine, _ = world
    manifest = manager_create(world, None)
    report = engine.reconcile(manifest)
    assert report.ok()
    outcome = engine.resume(report)
    assert outcome.action is RecoveryAction.RESUME
    assert outcome.stages[-1] == "resume"


def test_forged_verdict_cannot_sneak_drift(world) -> None:
    """A lying RESUME_READY header with error drift still raises."""
    _, _, engine, _ = world
    manifest = manager_create(world, None)
    forged = ReconciliationReport(
        checkpoint_id=manifest.checkpoint_id,
        verdict=RecoveryVerdict.RESUME_READY,
        drift=(
            Drift(
                surface=VerificationSurface.FILES,
                kind=DriftKind.FILE_MISSING,
                severity=DriftSeverity.ERROR,
                detail="README.md vanished",
            ),
        ),
    )
    with pytest.raises(NoBlindResumeError):
        engine.resume(forged)


def test_matched_surfaces_shrink_with_drift(world) -> None:
    repo, _, engine, _ = world
    manifest = manager_create(world, None)
    (repo / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    report = engine.reconcile(manifest)
    assert VerificationSurface.FILES not in report.matched
    assert set(report.matched) == set(VerificationSurface) - {VerificationSurface.FILES}
