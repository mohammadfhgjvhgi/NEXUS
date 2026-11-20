"""§22.1 — the disk checkpoint store: atomic, pruned, escape-proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.recovery import (
    CheckpointManifest,
    CheckpointNotFoundError,
    CheckpointScope,
    CorruptCheckpointError,
    DiskCheckpointStore,
    RecoveryError,
    TriggerEvent,
)


def _manifest(cid: str, scope: CheckpointScope, created: str) -> CheckpointManifest:
    return CheckpointManifest(
        checkpoint_id=cid,
        scope=scope,
        trigger=TriggerEvent.TASK_START,
        label="",
        created_at_utc=created,
        nexus_version="0.22.0",
        nexus_phase=22,
    )


def test_save_load_roundtrip(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path)
    manifest = _manifest("ck_task_20260212T101500Z_ab12", CheckpointScope.TASK,
                         "2026-02-12T10:15:00+00:00")
    store.save(manifest, {"notes.txt": b"hello"})
    loaded = store.load("ck_task_20260212T101500Z_ab12")
    assert loaded == manifest
    assert store.read_blob("ck_task_20260212T101500Z_ab12", "notes.txt") == b"hello"


def test_manifest_is_atomic_and_clean(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path)
    manifest = _manifest("ck_git_20260212T101501Z_cd34", CheckpointScope.GIT,
                         "2026-02-12T10:15:01+00:00")
    store.save(manifest)
    cdir = tmp_path / manifest.checkpoint_id
    assert (cdir / "manifest.json").is_file()
    assert not list(cdir.glob("*.tmp"))
    payload = json.loads((cdir / "manifest.json").read_text(encoding="utf-8"))
    assert payload["checkpoint_id"] == manifest.checkpoint_id


def test_not_found_and_corrupt(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path)
    with pytest.raises(CheckpointNotFoundError):
        store.load("ck_task_20260212T101502Z_ee55")
    manifest = _manifest("ck_task_20260212T101503Z_ff66", CheckpointScope.TASK,
                         "2026-02-12T10:15:03+00:00")
    store.save(manifest)
    target = tmp_path / manifest.checkpoint_id / "manifest.json"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptCheckpointError):
        store.load(manifest.checkpoint_id)


def test_bad_ids_refused(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path)
    with pytest.raises(RecoveryError):
        store.load("../escape")
    with pytest.raises(RecoveryError):
        store.read_blob("ck_task_20260212T101504Z_aa77", "../../outside.txt")


def test_list_latest_and_scope_filter(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path)
    a = _manifest("ck_task_20260212T101505Z_bb88", CheckpointScope.TASK,
                  "2026-02-12T10:15:05+00:00")
    b = _manifest("ck_git_20260212T101506Z_cc99", CheckpointScope.GIT,
                  "2026-02-12T10:15:06+00:00")
    c = _manifest("ck_task_20260212T101507Z_dd00", CheckpointScope.TASK,
                  "2026-02-12T10:15:07+00:00")
    for m in (c, a, b):  # deliberately out of order
        store.save(m)
    assert [m.checkpoint_id for m in store.list()] == [
        a.checkpoint_id, b.checkpoint_id, c.checkpoint_id
    ]
    assert [m.checkpoint_id for m in store.list("task")] == [a.checkpoint_id, c.checkpoint_id]
    assert store.latest().checkpoint_id == c.checkpoint_id
    assert store.latest("git").checkpoint_id == b.checkpoint_id
    assert store.latest("state") is None


def test_retention_prunes_per_scope(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path, keep_per_scope=2)
    ids = []
    for i in range(4):
        cid = f"ck_state_20260212T10151{i}Z_{i:04x}"
        ids.append(cid)
        store.save(_manifest(cid, CheckpointScope.STATE, f"2026-02-12T10:15:1{i}+00:00"))
    remaining = {m.checkpoint_id for m in store.list()}
    assert remaining == set(ids[-2:])


def test_restore_reapplies_files(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path)
    manifest = _manifest("ck_project_20260212T101509Z_abcd", CheckpointScope.PROJECT,
                         "2026-02-12T10:15:09+00:00")
    store.save(manifest, {"src/app.py": b"print(1)\n", "README.md": b"hi\n"})
    target = tmp_path / "restored"
    count = store.restore(manifest.checkpoint_id, target)
    assert count == 2
    assert (target / "src" / "app.py").read_bytes() == b"print(1)\n"


def test_blobs_listing(tmp_path: Path) -> None:
    store = DiskCheckpointStore(tmp_path)
    manifest = _manifest("ck_project_20260212T101510Z_bead", CheckpointScope.PROJECT,
                         "2026-02-12T10:15:10+00:00")
    assert store.blobs(manifest.checkpoint_id) == {}
    store.save(manifest, {"a.txt": b"1", "sub/b.txt": b"2"})
    blobs = store.blobs(manifest.checkpoint_id)
    assert sorted(blobs) == ["a.txt", "sub/b.txt"]
