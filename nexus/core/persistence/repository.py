"""Task persistence repository (Final Build Plan §2.5 / §2.6).

One JSON file per task under the ``tasks`` directory, written atomically
(temp file + ``os.replace``) so a crash can never leave a half-written
record. A small ``index.json`` keeps fast listings. Task ids are strictly
validated (``task_`` + 32 hex) before touching the filesystem — path
traversal is impossible by construction.

Lifecycle contract (§2.6): save → close NEXUS → open NEXUS → load → the
task continues from its persisted state, with its full session history.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..engine.states import TaskState
from ..session.models import Task
from .serializer import (
    TASK_RECORD_SCHEMA,
    TASK_RECORD_VERSION,
    PersistenceError,
    task_from_record,
    task_to_record,
)

_TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{32}$")

INDEX_SCHEMA = "nexus.tasks.index"
INDEX_VERSION = 1


@dataclass(frozen=True, slots=True)
class TaskSummary:
    """Listing entry (fast index view of one task)."""

    id: str
    state: TaskState
    goal: str
    workspace: str
    updated_at: datetime


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())  # survive power loss before the rename
    os.replace(tmp_path, path)


def _summary_of(task: Task) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        state=task.state,
        goal=task.goal,
        workspace=task.workspace,
        updated_at=task.updated_at,
    )


class TaskRepository:
    """Filesystem-backed task store (atomic, single-writer)."""

    def __init__(self, tasks_dir: str | Path, *, create: bool = True) -> None:
        self._tasks_dir = Path(tasks_dir)
        if create:
            self._tasks_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- internals

    @property
    def tasks_dir(self) -> Path:
        return self._tasks_dir

    def _task_path(self, task_id: str) -> Path:
        if not _TASK_ID_PATTERN.match(task_id):
            raise PersistenceError(
                f"invalid task id {task_id!r} — expected task_<32 hex>"
            )
        return self._tasks_dir / f"{task_id}.json"

    def _index_path(self) -> Path:
        return self._tasks_dir / "index.json"

    def _read_index(self) -> list[TaskSummary]:
        path = self._index_path()
        if not path.is_file():
            return []
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            raise PersistenceError(f"failed to read {path}: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema") != INDEX_SCHEMA:
            raise PersistenceError(f"{path}: not a {INDEX_SCHEMA} file")
        summaries: list[TaskSummary] = []
        for entry in data.get("tasks", []):
            try:
                summaries.append(
                    TaskSummary(
                        id=str(entry["id"]),
                        state=TaskState(str(entry["state"])),
                        goal=str(entry.get("goal", "")),
                        workspace=str(entry.get("workspace", "main")),
                        updated_at=datetime.fromisoformat(
                            str(entry["updated_at"])
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PersistenceError(
                    f"{path}: corrupt index entry {entry!r} ({exc})"
                ) from exc
        return summaries

    def _write_index(self, summaries: list[TaskSummary]) -> None:
        ordered = sorted(
            summaries, key=lambda summary: summary.updated_at, reverse=True
        )
        data = {
            "schema": INDEX_SCHEMA,
            "schema_version": INDEX_VERSION,
            "tasks": [
                {
                    "id": summary.id,
                    "state": summary.state.value,
                    "goal": summary.goal,
                    "workspace": summary.workspace,
                    "updated_at": summary.updated_at.isoformat(),
                }
                for summary in ordered
            ],
        }
        _atomic_write_json(self._index_path(), data)

    # ----------------------------------------------------------------- reads

    def exists(self, task_id: str) -> bool:
        return self._task_path(task_id).is_file()

    def load(self, task_id: str) -> Task:
        """Load one task by id (validated against traversal)."""
        path = self._task_path(task_id)
        if not path.is_file():
            raise PersistenceError(f"no persisted task {task_id!r}")
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            raise PersistenceError(f"failed to read {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise PersistenceError(
                f"{path}: expected a JSON object, got {type(data).__name__}"
            )
        return task_from_record(data)

    def list_summaries(self) -> list[TaskSummary]:
        """List tasks from the index; a missing **or corrupt** index is
        rebuilt by scanning the task records (self-healing)."""
        if self._index_path().is_file():
            try:
                return self._read_index()
            except PersistenceError:
                pass  # corrupt index → rebuild below
        return self._rebuild_index()

    def _rebuild_index(self) -> list[TaskSummary]:
        """Rebuild the index by scanning task records (skips corrupt ones)."""
        summaries: list[TaskSummary] = []
        for path in sorted(self._tasks_dir.glob("task_*.json")):
            try:
                task = self.load(path.stem)
            except PersistenceError:
                continue
            summaries.append(_summary_of(task))
        self._write_index(summaries)
        return sorted(summaries, key=lambda s: s.updated_at, reverse=True)

    # ---------------------------------------------------------------- writes

    def save(self, task: Task) -> Path:
        """Persist a task atomically and refresh the index; returns the
        record path."""
        path = self._task_path(task.id)
        record = task_to_record(task)
        _atomic_write_json(path, record)
        self._write_index(self._merge_index(_summary_of(task)))
        return path

    def _merge_index(self, summary: TaskSummary) -> list[TaskSummary]:
        try:
            summaries = [
                existing
                for existing in self._read_index()
                if existing.id != summary.id
            ]
        except PersistenceError:
            # corrupt index must never wedge saves — rebuild by scanning
            summaries = [
                existing
                for existing in self._rebuild_index()
                if existing.id != summary.id
            ]
        summaries.append(summary)
        return summaries

    # -------------------------------------------------------------- lifecycle

    def close(self) -> None:
        """Close the repository. Writes are atomic, so there are no open
        handles to flush; provided for Runtime.shutdown symmetry."""
        return None


def record_envelope() -> dict[str, Any]:
    """Envelope constants of the task record format (documentation aid)."""
    return {
        "schema": TASK_RECORD_SCHEMA,
        "schema_version": TASK_RECORD_VERSION,
        "index_schema": INDEX_SCHEMA,
        "index_version": INDEX_VERSION,
    }
