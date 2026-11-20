"""Checkpoint Manager + Trigger Events (New Plan §22.1–§22.2).

§22.1 — one manager, four scopes::

    Task · Project · Git · State

§22.2 — six trigger events, each one a checkpoint (periodic gated by
an interval policy)::

    task start · phase complete · major change · critical test ·
    before risky change · periodic

The capture is honest on both ends: the file inventory and the git
head are read from the real tree, the environment expectations
(processes · windows · browser) are captured from the live probes and
stored inside the manifest so §22.4 reconciliation has a baseline to
compare against — that baseline is *data on disk*, not memory.

Stdlib only.
"""

from __future__ import annotations

import secrets as _secrets
from collections.abc import Callable
from pathlib import Path

from .contracts import (
    CheckpointManifest,
    CheckpointScope,
    TriggerEvent,
    utc_now_iso,
)
from .probes import (
    GitProbe,
    WindowProbe,
    browser_markers,
    capture_expectations,
    inventory_files,
    sha256_bytes,
)
from .store import DiskCheckpointStore, new_checkpoint_id

ExpectationsProvider = Callable[
    [], tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]
]


class TriggerPolicy:
    """Decides whether an event earns a checkpoint — periodic-aware."""

    def __init__(
        self,
        min_interval_seconds: float = 300.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time

        self._min = float(min_interval_seconds)
        self._clock = clock or time.monotonic
        self._last_periodic: float | None = None

    def allows(self, event: TriggerEvent) -> bool:
        if event is not TriggerEvent.PERIODIC:
            return True
        now = self._clock()
        if self._last_periodic is None or (now - self._last_periodic) >= self._min:
            self._last_periodic = now
            return True
        return False


class CheckpointManager:
    """§22.1 capture across the four scopes · §22.2 trigger entry."""

    def __init__(
        self,
        store: DiskCheckpointStore,
        repo_root: Path,
        *,
        version: str = "",
        phase: int = 0,
        triggers: TriggerPolicy | None = None,
        expectations_provider: ExpectationsProvider | None = None,
        max_file_bytes: int = 2_000_000,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._store = store
        self._root = Path(repo_root)
        self._version = version
        self._phase = phase
        self._triggers = triggers or TriggerPolicy()
        self._expectations = expectations_provider or self._live_expectations
        self._max = max_file_bytes
        self._id_factory = id_factory or self._default_id
        self.created: list[CheckpointManifest] = []

    # ------------------------------------------------------------ public

    def create(
        self,
        scope: CheckpointScope,
        trigger: TriggerEvent,
        label: str = "",
        task_state: dict | None = None,
        extra_state: dict | None = None,
    ) -> CheckpointManifest:
        """Capture one checkpoint — the §22.1 four targets."""
        git = GitProbe(self._root)
        head, branch, dirty, _notes = git.probe()

        files_inventory: dict[str, str] = {}
        blobs: dict[str, bytes] = {}
        if scope in (CheckpointScope.PROJECT, CheckpointScope.GIT):
            files_inventory = inventory_files(self._root, self._max)
            for rel in files_inventory:
                path = self._root / rel
                try:
                    blobs[rel] = path.read_bytes()
                except OSError:
                    blobs.pop(rel, None)
                    files_inventory.pop(rel, None)

        state: dict = {
            "task_state": dict(task_state or {}),
            "environment": capture_expectations(*self._expectations()),
        }
        if scope is CheckpointScope.GIT:
            state["git_dirty"] = dirty
        if extra_state:
            state.update(extra_state)

        now = utc_now_iso()
        manifest = CheckpointManifest(
            checkpoint_id=self._id_factory(scope.value),
            scope=scope,
            trigger=trigger,
            label=label,
            created_at_utc=now,
            nexus_version=self._version,
            nexus_phase=self._phase,
            git_head=head,
            git_branch=branch,
            files=tuple(
                type(self)._file_entry(rel, digest) for rel, digest in files_inventory.items()
            ),
            state=state,
        )
        self._store.save(manifest, blobs)
        self.created.append(manifest)
        return manifest

    def on_event(
        self,
        event: TriggerEvent,
        label: str = "",
        scope: CheckpointScope = CheckpointScope.TASK,
        task_state: dict | None = None,
    ) -> CheckpointManifest | None:
        """§22.2 — one entry for all six triggers.

        Every non-periodic event captures immediately; ``periodic``
        flows through the interval policy and may honestly decline.
        """
        if not self._triggers.allows(event):
            return None
        return self.create(scope=scope, trigger=event, label=label, task_state=task_state)

    def latest(self, scope: CheckpointScope | None = None) -> CheckpointManifest | None:
        return self._store.latest(scope.value if scope else None)

    @property
    def store(self) -> DiskCheckpointStore:
        return self._store

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _file_entry(rel: str, digest: str):
        from .contracts import FileEntry

        return FileEntry(path=rel, sha256=digest, size=-1)

    @staticmethod
    def _default_id(scope: str) -> str:
        return new_checkpoint_id(scope, utc_now_iso(), _secrets.token_hex(2))

    @staticmethod
    def _live_expectations() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Real capture — processes + windows + browser markers.

        A failing host probe degrades to empty expectations honestly
        (the manifest notes nothing it did not see).
        """
        try:
            from .probes import ProcessProbe

            procs = ProcessProbe().probe()
        except Exception:  # noqa: BLE001 — capture never blocks the checkpoint
            procs = ()
        try:
            windows = WindowProbe().probe()
        except Exception:  # noqa: BLE001
            windows = ()
        return procs, windows, browser_markers(procs)


def file_blobs_of(manifest: CheckpointManifest, store: DiskCheckpointStore) -> dict[str, bytes]:
    """Blobs keyed by the manifest's file paths (digest-checked)."""
    out: dict[str, bytes] = {}
    for entry in manifest.files:
        try:
            data = store.read_blob(manifest.checkpoint_id, entry.path)
        except Exception:  # noqa: BLE001 — missing blob handled upstream
            continue
        if sha256_bytes(data) == entry.sha256:
            out[entry.path] = data
    return out
