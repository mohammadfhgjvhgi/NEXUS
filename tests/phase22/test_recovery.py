"""§22.3+§22.4 — the Recovery Engine: the chain and the six-surface law."""

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
    DriftKind,
    DriftSeverity,
    ProcessProbe,
    RecoveryAction,
    RecoveryVerdict,
    TriggerEvent,
    TriggerPolicy,
    VerificationSurface,
    WindowProbe,
    inventory_files,
)
from nexus.recovery.engine import RecoveryEngine, verify_tree


class _HarnessProbe:
    """The real probe, wrapped — a test may override single surfaces
    to simulate one machine change at a time (process died, window
    closed, …).  Every call still counts as a live measurement."""

    def __init__(self, base: CompositeProbe) -> None:
        self._base = base
        self.override: dict = {}
        self.calls = 0

    def probe(self):  # noqa: ANN202
        self.calls += 1
        facts = self._base.probe()
        if self.override:
            return dataclasses.replace(facts, **self.override)
        return facts


def _build(tmp_path: Path, repo: Path):
    store = DiskCheckpointStore(tmp_path / "checkpoints")
    manager = CheckpointManager(
        store, repo, version="0.22.0", phase=22,
        triggers=TriggerPolicy(min_interval_seconds=0),
        expectations_provider=lambda: ((), (), ()),
    )
    state_path = tmp_path / "task_state.json"
    state_path.write_text(
        json.dumps({"task": "T-1", "state": "RUNNING"}), encoding="utf-8"
    )
    base = CompositeProbe(
        repo,
        state_path,
        processes=ProcessProbe(runner=lambda argv: ""),
        windows=WindowProbe(runner=lambda argv: ""),
    )
    engine = RecoveryEngine(store, repo, state_path, probe=_HarnessProbe(base))
    return manager, engine, state_path


def test_happy_path_resume(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state={"task": "T-1", "state": "RUNNING"},
    )
    outcome = engine.recover(manifest.checkpoint_id)
    assert outcome.action is RecoveryAction.RESUME
    assert outcome.report.ok()
    assert outcome.report.verdict is RecoveryVerdict.RESUME_READY
    assert set(outcome.report.matched) == set(VerificationSurface)
    assert outcome.stages[-1] == "resume"
    assert outcome.restored_files == 0


def test_file_modified_blocks_then_repairs(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state={"task": "T-1", "state": "RUNNING"},
    )
    (repo / "src" / "app.py").write_text("print('drifted')\n", encoding="utf-8")

    outcome = engine.recover(manifest.checkpoint_id, repair=False)
    assert outcome.action is RecoveryAction.RESTART_TASK
    assert any(d.kind is DriftKind.FILE_MODIFIED for d in outcome.report.drift)

    outcome2 = engine.recover(manifest.checkpoint_id, repair=True)
    assert outcome2.action is RecoveryAction.RESUME
    assert outcome2.restored_files >= 1
    assert "nexus-22" in (repo / "src" / "app.py").read_text(encoding="utf-8")
    assert "resumed after repair" in outcome2.detail


def test_file_missing_is_repaired_from_blob(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.CRITICAL_TEST,
        task_state={"task": "T-1", "state": "RUNNING"},
    )
    (repo / "README.md").unlink()
    outcome = engine.recover(manifest.checkpoint_id, repair=True)
    assert outcome.action is RecoveryAction.RESUME
    assert (repo / "README.md").exists()


def test_extra_file_is_warning_only(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.MAJOR_CHANGE,
        task_state={"task": "T-1", "state": "RUNNING"},
    )
    (repo / "new_artifact.txt").write_text("later work\n", encoding="utf-8")
    outcome = engine.recover(manifest.checkpoint_id, repair=False)
    assert outcome.action is RecoveryAction.RESUME
    warnings = [d for d in outcome.report.drift if d.severity is DriftSeverity.WARNING]
    assert any(d.kind is DriftKind.FILE_EXTRA for d in warnings)
    assert outcome.report.ok()  # warnings annotate; errors block


def test_git_divergence_never_blind_resumes(repo: Path, tmp_path: Path) -> None:
    if shutil.which("git") is None:  # pragma: no cover
        pytest.skip("git binary unavailable on this host")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@n.dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "n"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)

    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state={"task": "T-1", "state": "RUNNING"},
    )
    (repo / "later.txt").write_text("new commit\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "second"], check=True)

    outcome = engine.recover(manifest.checkpoint_id, repair=True)
    assert outcome.action is not RecoveryAction.RESUME  # the §22.4 wall
    assert any(d.kind is DriftKind.GIT_DIVERGED for d in outcome.report.drift)


def test_process_death_blocks_resume(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.TASK, TriggerEvent.TASK_START,
        task_state={"task": "T-1", "state": "RUNNING"},
        extra_state={"environment": {"processes": ["companion-agent"],
                                     "windows": [], "browser": []}},
    )
    engine._probe.override = {"processes": ()}  # the companion died
    outcome = engine.recover(manifest.checkpoint_id, repair=True)
    engine._probe.override = {}
    assert outcome.action is RecoveryAction.RESTART_TASK
    assert any(d.kind is DriftKind.PROCESS_DEAD for d in outcome.report.drift)
    assert VerificationSurface.PROCESSES not in outcome.report.matched


def test_window_close_blocks_resume(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.TASK, TriggerEvent.TASK_START,
        task_state={"task": "T-1", "state": "RUNNING"},
        extra_state={"environment": {"processes": [], "windows": ["Build output"],
                                     "browser": []}},
    )
    engine._probe.override = {"windows": ("unrelated",)}  # the tracked one closed
    outcome = engine.recover(manifest.checkpoint_id, repair=True)
    engine._probe.override = {}
    assert outcome.action is RecoveryAction.RESTART_TASK
    assert any(d.kind is DriftKind.WINDOW_CLOSED for d in outcome.report.drift)


def test_browser_change_blocks_resume(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.TASK, TriggerEvent.TASK_START,
        task_state={"task": "T-1", "state": "RUNNING"},
        extra_state={"environment": {"processes": [], "windows": [],
                                     "browser": ["chrome"]}},
    )
    engine._probe.override = {"browser": ()}
    outcome = engine.recover(manifest.checkpoint_id, repair=True)
    engine._probe.override = {}
    assert outcome.action is RecoveryAction.RESTART_TASK
    assert any(d.kind is DriftKind.BROWSER_CHANGED for d in outcome.report.drift)


def test_task_state_mismatch_blocks_resume(repo: Path, tmp_path: Path) -> None:
    manager, engine, state_path = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.TASK, TriggerEvent.TASK_START,
        task_state={"task": "T-1", "state": "RUNNING"},
    )
    state_path.write_text(
        json.dumps({"task": "T-1", "state": "CRASHED"}), encoding="utf-8"
    )
    outcome = engine.recover(manifest.checkpoint_id, repair=True)
    assert outcome.action is RecoveryAction.RESTART_TASK
    assert any(d.kind is DriftKind.TASK_STATE_MISMATCH for d in outcome.report.drift)


def test_unrecoverable_when_checkpoint_gone(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    outcome = engine.recover("ck_task_20260212T101599Z_dead", repair=True)
    assert outcome.action is RecoveryAction.ABORT
    assert outcome.report.verdict is RecoveryVerdict.UNRECOVERABLE
    assert outcome.stages == (
        "crash", "checkpoint", "actual_environment", "reconciliation",
    )


def test_corrupt_manifest_is_unrecoverable(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(CheckpointScope.TASK, TriggerEvent.PERIODIC)
    target = manager.store.root / manifest.checkpoint_id / "manifest.json"
    target.write_text("{{{", encoding="utf-8")
    outcome = engine.recover(manifest.checkpoint_id)
    assert outcome.action is RecoveryAction.ABORT
    assert outcome.report.verdict is RecoveryVerdict.UNRECOVERABLE


def test_reconcile_always_measures_live(repo: Path, tmp_path: Path) -> None:
    manager, engine, _ = _build(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.TASK, TriggerEvent.TASK_START,
        task_state={"task": "T-1", "state": "RUNNING"},
    )
    calls_before = engine._probe.calls
    engine.recover(manifest.checkpoint_id)
    assert engine._probe.calls > calls_before  # the actual environment was measured


def test_verify_tree_standalone(repo: Path) -> None:
    expected = inventory_files(repo)
    ok, drift = verify_tree(repo, expected)
    assert ok and drift == {}
    (repo / "README.md").write_text("x", encoding="utf-8")
    ok, drift = verify_tree(repo, expected)
    assert not ok and drift == {"README.md": "modified"}
