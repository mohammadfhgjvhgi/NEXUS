"""Goal persistence + long-running state (PHASE 25 §25.1 + §25.3).

§25.1 — the goal is **persisted**, not remembered: every goal lives in
its own directory as ``goal.json`` written atomically (temp file +
``os.replace`` + ``fsync`` — the §6.4/§22 house pattern), plus an
append-only ``progress.jsonl`` journal.  A rebooted process constructs
a fresh :class:`GoalStore` over the same directory and finds every
goal exactly as the dying one left it — the goal survives, «اشتغل لحد
ما تخلص» survives with it.

§25.3 — the long-running state is the ladder in
:data:`~nexus.horizon.contracts.GOAL_STATES` with the transition law in
:data:`~nexus.horizon.contracts.TRANSITIONS`: an illegal transition
raises :class:`IllegalTransitionError` instead of silently bending the
ladder.  Every write goes through the store, every read comes from
disk — the state is durable between steps, so a mid-run reader (or a
successor process) sees the truth, not a stale memory.

The store is thread-safe (one lock around read-modify-write — several
runners may share it in-process; across processes the §25.6 generation
lease is the guard).

Stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

from .contracts import (
    GOAL_STATES,
    TRANSITIONS,
    GoalRecord,
    HorizonError,
    IllegalTransitionError,
    ProgressNote,
    UnknownGoalError,
    new_goal_id,
)

logger = logging.getLogger("nexus.horizon")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class GoalStore:
    """§25.1 + §25.3 — durable goals, durable state, on one disk."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._lock = threading.Lock()

    # ------------------------------------------------------------- paths

    @property
    def directory(self) -> Path:
        return self._directory

    def goal_dir(self, goal_id: str) -> Path:
        return self._directory / goal_id

    def goal_path(self, goal_id: str) -> Path:
        return self.goal_dir(goal_id) / "goal.json"

    def progress_path(self, goal_id: str) -> Path:
        return self.goal_dir(goal_id) / "progress.jsonl"

    # -------------------------------------------------------------- 25.1

    def create_goal(self, statement: str, deadline: str) -> GoalRecord:
        """Persist a new goal (state ``pending``) — atomically."""
        goal_id = new_goal_id()
        record = GoalRecord(
            goal_id=goal_id,
            statement=statement,
            deadline=deadline,
            state="pending",
            created_at=_utc_now_iso(),
            updated_at=_utc_now_iso(),
        )
        with self._lock:
            self._write(record)
        logger.debug("goal %s created (%s)", goal_id, deadline)
        return record

    def get(self, goal_id: str) -> GoalRecord:
        """Read the goal from disk — never from memory."""
        path = self.goal_path(goal_id)
        if not path.exists():
            raise UnknownGoalError(f"no goal persisted at {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HorizonError(
                f"goal {goal_id!r} state is unreadable on disk: {exc}"
            ) from exc
        return GoalRecord.from_dict(data)

    def list_goals(self) -> tuple[GoalRecord, ...]:
        """Every persisted goal, ordered by id (stable)."""
        if not self._directory.exists():
            return ()
        records = []
        for entry in sorted(self._directory.iterdir()):
            path = entry / "goal.json"
            if not entry.is_dir() or not path.exists():
                continue
            try:
                records.append(GoalRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError, HorizonError, KeyError) as exc:
                logger.warning("skipping unreadable goal %s: %s", entry.name, exc)
        return tuple(records)

    def exists(self, goal_id: str) -> bool:
        return self.goal_path(goal_id).exists()

    # -------------------------------------------------------------- 25.3

    def transition(self, goal_id: str, new_state: str) -> GoalRecord:
        """Move the goal along the §25.3 ladder — or refuse loudly."""
        if new_state not in GOAL_STATES:
            raise HorizonError(
                f"unknown state {new_state!r} — the ladder is {GOAL_STATES}"
            )
        with self._lock:
            record = self.get(goal_id)
            allowed = TRANSITIONS[record.state]
            if new_state not in allowed:
                raise IllegalTransitionError(
                    f"goal {goal_id}: {record.state!r} → {new_state!r} is not"
                    f" on the ladder (allowed: {sorted(allowed)})"
                )
            updated = GoalRecord(
                goal_id=record.goal_id,
                statement=record.statement,
                deadline=record.deadline,
                state=new_state,
                created_at=record.created_at,
                updated_at=_utc_now_iso(),
                progress_seq=record.progress_seq,
                last_checkpoint_id=record.last_checkpoint_id,
                generation=record.generation,
                deadline_at=record.deadline_at,
            )
            self._write(updated)
            return updated

    def begin_run(self, goal_id: str, *, deadline_at: float | None) -> GoalRecord:
        """Open a run: state → ``running``, a fresh deadline window, and
        a bumped generation (the durable lease — the newest runner owns
        the goal; the superseded one retires itself at its next step).

        Allowed from any resumable/pending state — the caller
        (:mod:`nexus.horizon.runner` / ``.resume``) owns the policy; the
        store owns atomicity and the ladder's ``running`` entry.
        """
        with self._lock:
            record = self.get(goal_id)
            updated = GoalRecord(
                goal_id=record.goal_id,
                statement=record.statement,
                deadline=record.deadline,
                state="running",
                created_at=record.created_at,
                updated_at=_utc_now_iso(),
                progress_seq=record.progress_seq,
                last_checkpoint_id=record.last_checkpoint_id,
                generation=record.generation + 1,
                deadline_at=deadline_at,
            )
            self._write(updated)
            logger.debug("goal %s run opened (generation %d)", goal_id, updated.generation)
            return updated

    def set_checkpoint(self, goal_id: str, checkpoint_id: str | None) -> GoalRecord:
        """Record the newest §22 checkpoint id with the goal (§25.5)."""
        with self._lock:
            record = self.get(goal_id)
            updated = GoalRecord(
                goal_id=record.goal_id,
                statement=record.statement,
                deadline=record.deadline,
                state=record.state,
                created_at=record.created_at,
                updated_at=_utc_now_iso(),
                progress_seq=record.progress_seq,
                last_checkpoint_id=checkpoint_id,
                generation=record.generation,
                deadline_at=record.deadline_at,
            )
            self._write(updated)
            return updated

    # -------------------------------------------------------- the journal

    def append_progress(self, goal_id: str, message: str) -> ProgressNote:
        """Append one journal line and bump ``progress_seq`` atomically."""
        if not message.strip():
            raise HorizonError("a progress note must be non-empty")
        with self._lock:
            record = self.get(goal_id)
            note = ProgressNote(
                seq=record.progress_seq + 1, ts=_utc_now_iso(), message=message
            )
            path = self.progress_path(goal_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(note.as_dict(), ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            updated = GoalRecord(
                goal_id=record.goal_id,
                statement=record.statement,
                deadline=record.deadline,
                state=record.state,
                created_at=record.created_at,
                updated_at=_utc_now_iso(),
                progress_seq=note.seq,
                last_checkpoint_id=record.last_checkpoint_id,
                generation=record.generation,
                deadline_at=record.deadline_at,
            )
            self._write(updated)
            return note

    def progress(self, goal_id: str) -> tuple[ProgressNote, ...]:
        """The full journal from disk, in seq order."""
        path = self.progress_path(goal_id)
        if not path.exists():
            return ()
        notes: list[ProgressNote] = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    notes.append(ProgressNote.from_dict(json.loads(line)))
                except json.JSONDecodeError as exc:
                    logger.warning("progress line unreadable (%s) — skipped", exc)
        return tuple(notes)

    # ------------------------------------------------------------- write

    def _write(self, record: GoalRecord) -> None:
        """Atomic write (temp + replace + fsync) — the house pattern."""
        path = self.goal_path(record.goal_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(record.as_dict(), ensure_ascii=False, indent=2) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=".goal.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def load_store(directory: str | Path) -> GoalStore:
    """Construct a store over an existing directory (the reboot path —
    §25.1: the same dir yields the same goals, from disk only)."""
    return GoalStore(directory)
