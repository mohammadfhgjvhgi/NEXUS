"""Coding session trail (New Plan §15.5 — Cline MODE D inspiration).

Cline's durable session record — *which files were read, which were
edited, every tool call, the commits the task produced* — adapted to
NEXUS-native shapes (zero imports from the reference; the study lives
in ``vendor-staging/phase-15/cline``).

The :class:`CodingSession` owns a :class:`CodingSessionRecord` and
persists it as atomic JSON (temp file + ``os.replace`` + ``fsync`` —
the house discipline) under a session directory. Commit linking goes
through the nexus git module when its API grows one; today the seat
is a placeholder, so the trail records what exists and never fakes a
commit.

سجل جلسة البرمجة — ما قُرئ وما عُدّل وكل نداء أداة؛ كتابة ذرّية
على القرص والربط بوحدة git متى نضجت.

Stdlib only.
"""

from __future__ import annotations

import importlib
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .contracts import CodingSessionRecord, ToolCallRecord

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: Session ids: ``cs_`` + 12 hex chars (the ``task_``/``ag_`` family).
def new_session_id() -> str:
    return "cs_" + secrets.token_hex(6)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


#: Session statuses (open → closed/failed).
SESSION_STATUSES: tuple[str, ...] = ("open", "closed", "failed")


class CodingSessionError(Exception):
    """Coding-session misuse (unknown record, unreadable file…)."""


class CodingSession:
    """One coding session's trail — read it, write it, persist it.

    ``directory`` — where the JSON record lives; ``None`` means an
    in-memory trail only (no persistence).
    """

    def __init__(
        self,
        goal: str = "",
        *,
        session_id: str | None = None,
        directory: str | Path | None = None,
        record: CodingSessionRecord | None = None,
    ) -> None:
        self._directory = Path(directory) if directory is not None else None
        if record is not None:
            self._record = record
        else:
            self._record = CodingSessionRecord(
                session_id=session_id or new_session_id(),
                goal=goal,
                started_at=_now_iso(),
                updated_at=_now_iso(),
                status="open",
            )
        if self._directory is not None:
            self._directory.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------- trail

    @property
    def record(self) -> CodingSessionRecord:
        return self._record

    @property
    def session_id(self) -> str:
        return self._record.session_id

    @property
    def directory(self) -> Path | None:
        return self._directory

    @property
    def files_read(self) -> tuple[str, ...]:
        return self._record.files_read

    @property
    def files_edited(self) -> tuple[str, ...]:
        return self._record.files_edited

    @property
    def tool_calls(self) -> tuple[ToolCallRecord, ...]:
        return self._record.tool_calls

    @property
    def commits(self) -> tuple[str, ...]:
        return self._record.commits

    def note_read(self, path: str) -> None:
        """A file was read — first-seen order, no duplicates."""
        normalized = str(path).replace("\\", "/")
        if normalized and normalized not in self._record.files_read:
            self._record.files_read = (*self._record.files_read, normalized)
            self._touch()

    def note_edit(self, path: str) -> None:
        """A file was changed — first-seen order, no duplicates."""
        normalized = str(path).replace("\\", "/")
        if normalized and normalized not in self._record.files_edited:
            self._record.files_edited = (*self._record.files_edited, normalized)
            self._touch()

    def note_tool_call(self, call: ToolCallRecord) -> None:
        """One tool call observed (name, detail, ok, duration)."""
        self._record.tool_calls = (*self._record.tool_calls, call)
        self._touch()

    def link_commit(self, commit_id: str) -> None:
        """Attach a task commit to the trail (git-module id)."""
        commit_id = str(commit_id).strip()
        if commit_id and commit_id not in self._record.commits:
            self._record.commits = (*self._record.commits, commit_id)
            self._touch()

    def close(self, status: str = "closed") -> CodingSessionRecord:
        """Seal the session (and persist when a directory was given)."""
        if status not in SESSION_STATUSES:
            raise CodingSessionError(
                f"status must be one of {SESSION_STATUSES}, got {status!r}"
            )
        self._record.status = status
        self._touch()
        if self._directory is not None:
            self.save()
        return self._record

    def _touch(self) -> None:
        self._record.updated_at = _now_iso()

    # ------------------------------------------------------ persistence

    @property
    def path(self) -> Path | None:
        if self._directory is None:
            return None
        return self._directory / f"{self._record.session_id}.json"

    def to_dict(self) -> dict[str, Any]:
        return self._record.to_dict()

    def save(self) -> Path:
        """Atomic JSON write — returns the record path."""
        target = self.path
        if target is None:
            raise CodingSessionError(
                "in-memory session (no directory) — construct with directory= to persist"
            )
        payload = {
            "schema": "nexus.coding.session/1",
            "record": self._record.to_dict(),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        assert self._directory is not None  # path is None otherwise (checked above)
        self._directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._directory), prefix=f".{target.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return target

    @classmethod
    def load(cls, path: str | Path) -> CodingSession:
        """Reopen a persisted session (the restart-continuity path)."""
        target = Path(path)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CodingSessionError(f"unreadable session record: {target}") from exc
        record_data: Mapping[str, Any] = data.get("record") or data
        record = CodingSessionRecord.from_dict(record_data)
        return cls(record=record, directory=target.parent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CodingSession:
        return cls(record=CodingSessionRecord.from_dict(data))


def discover_task_commits(root: str | Path) -> tuple[str, ...]:
    """Task commits via the nexus git module — honestly empty until it ships.

    The git seat (``nexus/git/``) is a phase-15 placeholder: the module
    imports as an empty namespace package with no API, so this returns
    ``()`` rather than shelling out behind the abstraction's back. The
    moment the module grows a real history/commits API, sessions link
    through it here.
    """
    try:
        module = importlib.import_module("nexus.git")
    except Exception:  # noqa: BLE001 — availability probe
        return ()
    for attr in ("task_commits", "list_commits", "log"):
        candidate = getattr(module, attr, None)
        if callable(candidate):
            try:
                answer = candidate(str(root))
            except Exception:  # noqa: BLE001 — probe discipline
                return ()
            if isinstance(answer, (list, tuple)):
                return tuple(str(item) for item in answer)
    return ()


def link_task_commits(
    session: CodingSession,
    root: str | Path,
    commits: Sequence[str] = (),
) -> tuple[str, ...]:
    """Link the session to task commits — explicit ids or the git module."""
    linked: list[str] = []
    for commit_id in commits:
        session.link_commit(commit_id)
        linked.append(str(commit_id))
    if not commits:
        for commit_id in discover_task_commits(root):
            session.link_commit(commit_id)
            linked.append(commit_id)
    return tuple(linked)
