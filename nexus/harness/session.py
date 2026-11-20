"""Agent session lifecycle (Plan §7.2 — the Cline session pattern, adapted).

The Cline SDK separates a *stateful core* from the agent loop and
gives every run a session with an explicit lifecycle. NEXUS adapts
the *pattern*: an :class:`AgentSession` is a tracked record with a
five-state machine::

    CREATED → ACTIVE ⇄ PAUSED → RESUMED ⇄ PAUSED → CLOSED
                 │              │
                 └──────────────┴────────→ CLOSED

* ``CREATED``  — registered, not yet driving (PAUSED/RESUMED not legal);
* ``ACTIVE``   — an agent loop is running inside this session;
* ``PAUSED``   — suspended (a §2.6 pause, a crash, a reboot);
* ``RESUMED``  — back in the loop after a pause (continuation; it is
  the active-after-pause status and may pause or close again);
* ``CLOSED``   — terminal; nothing transitions out of CLOSED.

Illegal transitions raise :class:`SessionTransitionError` — the same
honest-failure discipline as the §2.4 task machine. The tracker
persists under ``<data>/harness/sessions.json`` (atomic write) so a
reboot can list paused sessions and resume them; corrupt files reset
to empty (a boot never dies on a bad ledger).

Stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("nexus.harness")

#: The five lifecycle states (the Cline pattern, NEXUS vocabulary).
SESSION_STATUSES: tuple[str, ...] = (
    "CREATED",
    "ACTIVE",
    "PAUSED",
    "RESUMED",
    "CLOSED",
)

#: Legal transitions: status → allowed successors.
SESSION_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"ACTIVE", "CLOSED"}),
    "ACTIVE": frozenset({"PAUSED", "CLOSED"}),
    "PAUSED": frozenset({"RESUMED", "CLOSED"}),
    "RESUMED": frozenset({"PAUSED", "CLOSED"}),
    "CLOSED": frozenset(),
}

#: The §7.2 session record fields (harness-provable).
SESSION_FIELDS: tuple[str, ...] = (
    "id",
    "task_id",
    "agent_id",
    "status",
    "created_at",
    "updated_at",
    "turns",
    "note",
)


class SessionTransitionError(Exception):
    """Raised on an illegal session lifecycle transition."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class AgentSession:
    """One tracked agent session (the Cline lifecycle, NEXUS-owned)."""

    id: str
    task_id: str = ""
    agent_id: str = ""
    status: str = "CREATED"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    turns: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in SESSION_STATUSES:
            raise ValueError(f"unknown session status {self.status!r}")
        if not self.id:
            raise ValueError("session.id must be non-empty")

    def can_transition(self, target: str) -> bool:
        return target in SESSION_TRANSITIONS.get(self.status, frozenset())

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turns": self.turns,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AgentSession:
        return cls(
            id=str(data["id"]),
            task_id=str(data.get("task_id", "")),
            agent_id=str(data.get("agent_id", "")),
            status=str(data.get("status", "CREATED")),
            created_at=str(data.get("created_at", _now_iso())),
            updated_at=str(data.get("updated_at", _now_iso())),
            turns=int(data.get("turns", 0)),  # type: ignore[arg-type]
            note=str(data.get("note", "")),
        )


class SessionTracker:
    """The session ledger (Plan §7.2 pattern) with atomic persistence.

    ``begin`` registers CREATED and immediately transitions ACTIVE
    (the common entry); ``pause``/``resume``/``close`` move the machine;
    ``record_turn`` counts loop turns inside the active session.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / "harness" / "sessions.json"
        self._sessions: dict[str, AgentSession] = {}
        self._sequence = 0
        self._load()

    # ---------------------------------------------------------- persistence

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for item in raw.get("sessions", []):
                session = AgentSession.from_dict(item)
                self._sessions[session.id] = session
                suffix = session.id.rsplit("_", 1)[-1]
                if suffix.isdigit():
                    self._sequence = max(self._sequence, int(suffix))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("session ledger unreadable (%s) — reset to empty", exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sessions": [s.to_dict() for s in self._sessions.values()]}
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ------------------------------------------------------------- lifecycle

    def begin(self, *, task_id: str = "", agent_id: str = "",
              session_id: str | None = None) -> AgentSession:
        """Register a session and transition it straight to ACTIVE."""
        self._sequence += 1
        session = AgentSession(
            id=session_id
            or f"hs_{_now_iso().replace(':', '').replace('-', '')}_{self._sequence:04d}",
            task_id=task_id,
            agent_id=agent_id,
            status="CREATED",
        )
        self._sessions[session.id] = session
        self._transition(session, "ACTIVE")
        return session

    def _transition(self, session: AgentSession, target: str, *,
                    note: str = "") -> AgentSession:
        if not session.can_transition(target):
            raise SessionTransitionError(
                f"session {session.id}: {session.status} → {target} is illegal"
            )
        session.status = target
        session.updated_at = _now_iso()
        if note:
            session.note = note
        self._save()
        return session

    def pause(self, session_id: str, *, note: str = "") -> AgentSession:
        return self._transition(self.get(session_id), "PAUSED", note=note)

    def resume(self, session_id: str, *, note: str = "") -> AgentSession:
        """PAUSED → RESUMED: back inside the running loop (RESUMED *is*
        the active-after-pause status — it may pause or close again)."""
        return self._transition(self.get(session_id), "RESUMED", note=note)

    def close(self, session_id: str, *, note: str = "") -> AgentSession:
        return self._transition(self.get(session_id), "CLOSED", note=note)

    def record_turn(self, session_id: str) -> int:
        session = self.get(session_id)
        if session.status not in {"ACTIVE", "RESUMED"}:
            raise SessionTransitionError(
                f"session {session_id} is {session.status} — no turns run"
            )
        session.turns += 1
        session.updated_at = _now_iso()
        self._save()
        return session.turns

    # -------------------------------------------------------------- queries

    def get(self, session_id: str) -> AgentSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id!r}")
        return session

    def list(self) -> list[AgentSession]:
        return [self._sessions[key] for key in sorted(self._sessions)]

    def for_task(self, task_id: str) -> list[AgentSession]:
        return [s for s in self.list() if s.task_id == task_id]

    def paused(self) -> list[AgentSession]:
        return [s for s in self.list() if s.status == "PAUSED"]

    def latest_open(self, task_id: str) -> AgentSession | None:
        """The newest non-CLOSED session of a task (the resume target)."""
        candidates = [
            s
            for s in self._sessions.values()
            if s.task_id == task_id and s.status != "CLOSED"
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: (s.updated_at, s.id))
