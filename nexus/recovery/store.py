"""Disk checkpoint store (New Plan §22.1).

Layout, one directory per checkpoint::

    <root>/<checkpoint_id>/manifest.json     — the CheckpointManifest
    <root>/<checkpoint_id>/files/<relpath>   — the captured file blobs

Laws carried here:

* Everything lands on disk with timestamps — a checkpoint that lives
  only in memory is exactly what §22.4 forbids.
* Writes are atomic (tmp file + ``os.replace``) so a crash during
  checkpointing cannot corrupt the previous checkpoint.
* Blob paths are validated — a manifest may never address outside its
  own directory (the §21 security ethos applied to recovery).
* Retention: the newest ``keep_per_scope`` checkpoints per scope
  survive; older ones are pruned.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

from .contracts import (
    CheckpointManifest,
    CheckpointNotFoundError,
    CorruptCheckpointError,
    RecoveryError,
)

_MANIFEST_NAME = "manifest.json"
_FILES_DIR = "files"

#: checkpoint id — ``ck_<scope>_<utcstamp>_<4 hex>``
_ID_PATTERN = re.compile(r"^ck_[a-z]+_\d{8}T\d{6}Z_[0-9a-f]{4}$")


def new_checkpoint_id(scope: str, now_utc_iso: str, entropy: str) -> str:
    """Deterministic-from-inputs id builder (testable clock injection).

    ``now_utc_iso`` — any ISO instant; ``entropy`` — 4+ hex chars.
    """
    stamp = (
        now_utc_iso.replace("-", "").replace(":", "").split(".")[0].replace("+00:00", "Z")
    )
    if not stamp.endswith("Z"):
        stamp = stamp + "Z"
    return f"ck_{scope}_{stamp}_{entropy[:4]}"


class DiskCheckpointStore:
    """The on-disk home of every checkpoint (§22.1)."""

    def __init__(self, root: Path, keep_per_scope: int = 10) -> None:
        self._root = Path(root)
        self._keep = max(1, int(keep_per_scope))

    # ------------------------------------------------------------- paths

    @property
    def root(self) -> Path:
        return self._root

    def _dir(self, checkpoint_id: str) -> Path:
        if not _ID_PATTERN.match(checkpoint_id):
            raise RecoveryError(f"bad checkpoint id: {checkpoint_id!r}")
        return self._root / checkpoint_id

    def _blob_path(self, checkpoint_id: str, rel: str) -> Path:
        rel = rel.replace("\\", "/")
        if rel.startswith("/") or ".." in rel.split("/"):
            raise RecoveryError(f"blob path escapes the checkpoint: {rel!r}")
        return self._dir(checkpoint_id) / _FILES_DIR / rel

    # ------------------------------------------------------------- write

    def save(
        self,
        manifest: CheckpointManifest,
        blobs: Mapping[str, bytes] | None = None,
    ) -> str:
        """Persist manifest + blobs atomically; prune old ones after."""
        cdir = self._dir(manifest.checkpoint_id)
        cdir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2)
        tmp = cdir / (_MANIFEST_NAME + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, cdir / _MANIFEST_NAME)
        for rel, data in (blobs or {}).items():
            target = self._blob_path(manifest.checkpoint_id, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self._prune(manifest.scope.value)
        return manifest.checkpoint_id

    def _prune(self, scope: str) -> list[str]:
        manifests = [m for m in self.list() if m.scope.value == scope]
        manifests.sort(key=lambda m: m.created_at_utc, reverse=True)
        removed: list[str] = []
        for stale in manifests[self._keep :]:
            shutil.rmtree(self._dir(stale.checkpoint_id), ignore_errors=True)
            removed.append(stale.checkpoint_id)
        return removed

    # -------------------------------------------------------------- read

    def load(self, checkpoint_id: str) -> CheckpointManifest:
        manifest_path = self._dir(checkpoint_id) / _MANIFEST_NAME
        if not manifest_path.is_file():
            raise CheckpointNotFoundError(checkpoint_id)
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise CorruptCheckpointError(f"{checkpoint_id}: {exc}") from exc
        manifest = CheckpointManifest.from_dict(data)
        if manifest.checkpoint_id != checkpoint_id:
            raise CorruptCheckpointError(
                f"{checkpoint_id}: manifest claims {manifest.checkpoint_id}"
            )
        return manifest

    def exists(self, checkpoint_id: str) -> bool:
        try:
            return (self._dir(checkpoint_id) / _MANIFEST_NAME).is_file()
        except RecoveryError:
            return False

    def list(self, scope: str | None = None) -> tuple[CheckpointManifest, ...]:
        found: list[CheckpointManifest] = []
        if not self._root.is_dir():
            return ()
        for child in sorted(self._root.iterdir()):
            if not child.is_dir() or not _ID_PATTERN.match(child.name):
                continue
            try:
                manifest = self.load(child.name)
            except (CheckpointNotFoundError, CorruptCheckpointError):
                continue  # half-written checkpoint — honestly invisible
            if scope is None or manifest.scope.value == scope:
                found.append(manifest)
        found.sort(key=lambda m: m.created_at_utc)
        return tuple(found)

    def latest(self, scope: str | None = None) -> CheckpointManifest | None:
        every = self.list(scope)
        return every[-1] if every else None

    def read_blob(self, checkpoint_id: str, rel: str) -> bytes:
        target = self._blob_path(checkpoint_id, rel)
        if not target.is_file():
            raise CheckpointNotFoundError(f"{checkpoint_id}:{rel}")
        return target.read_bytes()

    def blobs(self, checkpoint_id: str) -> dict[str, bytes]:
        """Every stored blob of one checkpoint, keyed by rel path."""
        files_dir = self._dir(checkpoint_id) / _FILES_DIR
        out: dict[str, bytes] = {}
        if not files_dir.is_dir():
            return out
        for path in sorted(files_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(files_dir).as_posix()
                out[rel] = path.read_bytes()
        return out

    def restore(self, checkpoint_id: str, target: Path) -> int:
        """Re-apply the captured blobs onto ``target`` — the RESTART_TASK
        half of recovery.  Returns the number of files restored."""
        count = 0
        for rel, data in self.blobs(checkpoint_id).items():
            dest = Path(target) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            count += 1
        return count

    def delete(self, checkpoint_id: str) -> None:
        cdir = self._dir(checkpoint_id)
        if cdir.is_dir():
            shutil.rmtree(cdir)
