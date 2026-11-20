"""§22.1 — the Checkpoint Manager across the four scopes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.recovery import (
    CheckpointManager,
    CheckpointScope,
    DiskCheckpointStore,
    TriggerEvent,
    inventory_files,
)


def _manager(tmp_path: Path, repo: Path, **kwargs) -> CheckpointManager:
    return CheckpointManager(
        DiskCheckpointStore(tmp_path / "checkpoints", keep_per_scope=10),
        repo,
        version="0.22.0",
        phase=22,
        expectations_provider=lambda: (("python",), ("Editor",), ()),
        **kwargs,
    )


def test_project_scope_captures_files_and_blobs(tmp_path: Path, repo: Path) -> None:
    manager = _manager(tmp_path, repo)
    manifest = manager.create(CheckpointScope.PROJECT, TriggerEvent.MAJOR_CHANGE, label="snap")
    paths = {f.path for f in manifest.files}
    assert paths == {"README.md", "src/app.py"}
    blob = manager.store.read_blob(manifest.checkpoint_id, "src/app.py")
    assert blob == b"print('nexus-22')\n"
    assert manifest.scope is CheckpointScope.PROJECT
    assert manifest.trigger is TriggerEvent.MAJOR_CHANGE
    assert manifest.nexus_version == "0.22.0" and manifest.nexus_phase == 22


def test_git_scope_records_head_and_dirty(tmp_path: Path, repo: Path) -> None:
    git = shutil.which("git")
    if git is None:  # pragma: no cover — CI has git; honesty for bare hosts
        pytest.skip("git binary unavailable on this host")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@nexus.dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "nexus"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True)
    (repo / "README.md").write_text("dirty now\n", encoding="utf-8")

    manager = _manager(tmp_path, repo)
    manifest = manager.create(CheckpointScope.GIT, TriggerEvent.CRITICAL_TEST)
    assert manifest.git_head and len(manifest.git_head) == 40
    assert manifest.git_branch in {"main", "master"}
    assert manifest.state["git_dirty"] is True


def test_task_scope_carries_task_state(tmp_path: Path, repo: Path) -> None:
    manager = _manager(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.TASK,
        TriggerEvent.TASK_START,
        task_state={"id": "T-1", "state": "RUNNING", "آخر": "خطوة"},
    )
    assert manifest.files == ()  # task scope captures state, not the tree
    assert manifest.state["task_state"]["state"] == "RUNNING"
    assert manifest.state["task_state"]["آخر"] == "خطوة"


def test_state_scope_arbitrary_payload(tmp_path: Path, repo: Path) -> None:
    manager = _manager(tmp_path, repo)
    manifest = manager.create(
        CheckpointScope.STATE,
        TriggerEvent.PERIODIC,
        extra_state={"engine": {"cursor": 42}},
    )
    assert manifest.state["engine"] == {"cursor": 42}


def test_environment_expectations_captured(tmp_path: Path, repo: Path) -> None:
    manager = _manager(tmp_path, repo)
    manifest = manager.create(CheckpointScope.TASK, TriggerEvent.TASK_START)
    env = manifest.state["environment"]
    assert env["processes"] == ["python"]
    assert env["windows"] == ["Editor"]
    assert env["browser"] == []


def test_live_expectations_provider_is_honest(tmp_path: Path, repo: Path) -> None:
    manager = CheckpointManager(
        DiskCheckpointStore(tmp_path / "checkpoints"), repo,
        version="0.22.0", phase=22,
    )  # no injected provider — the real one runs
    manifest = manager.create(CheckpointScope.TASK, TriggerEvent.PERIODIC)
    env = manifest.state["environment"]
    assert isinstance(env["processes"], list)
    assert isinstance(env["windows"], list)
    assert isinstance(env["browser"], list)


def test_latest_and_store_passthrough(tmp_path: Path, repo: Path) -> None:
    manager = _manager(tmp_path, repo)
    first = manager.create(CheckpointScope.TASK, TriggerEvent.TASK_START, label="one")
    second = manager.create(CheckpointScope.TASK, TriggerEvent.CRITICAL_TEST, label="two")
    assert manager.latest(CheckpointScope.TASK).checkpoint_id == second.checkpoint_id
    assert manager.latest(CheckpointScope.PROJECT) is None
    assert first.label == "one"


def test_inventory_skips_noise(tmp_path: Path, repo: Path) -> None:
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\x00\x01")
    (repo / ".hidden").write_text("x\n", encoding="utf-8")
    (repo / "src" / "note.pyc").write_bytes(b"\x00")
    found = inventory_files(repo)
    assert set(found) == {"README.md", "src/app.py"}
