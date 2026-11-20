"""Persistent goals + heartbeats (Plan §7.4 — the Prime Agent pattern).

Prime Agent's long-horizon discipline: **goals** outlive single
tasks, **heartbeats** prove the loop is alive, and the harness keeps
both durable. NEXUS adapts the *pattern*:

* :class:`Goal` — a persistent objective with a four-state lifecycle
  (``active`` / ``paused`` / ``achieved`` / ``abandoned``) and an
  append-only progress log (each entry: timestamped note);
* :class:`GoalStore` — atomic JSON persistence under
  ``<data>/harness/goals.json``; a corrupt file resets to empty;
* :class:`Heartbeat` — the last-beat ledger per agent with
  ``stalled()`` detection (no beat within the interval ⇒ stall).

The full heartbeat/stall **system** is Plan §23 (PHASE 22); what
lands here is the harness-level pattern the later phase builds on.
Nothing imports Prime Agent.

Stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger("nexus.harness")

#: The four goal statuses (the Prime pattern, NEXUS vocabulary).
GOAL_STATUSES: tuple[str, ...] = (
    "active",
    "paused",
    "achieved",
    "abandoned",
)

#: The §7.4 goal record fields (harness-provable).
GOAL_FIELDS: tuple[str, ...] = (
    "id",
    "description",
    "status",
    "progress",
    "created_at",
    "updated_at",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class Goal:
    """One persistent long-horizon objective."""

    id: str
    description: str
    status: str = "active"
    progress: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("goal.id must be non-empty")
        if not self.description.strip():
            raise ValueError("goal.description must be non-empty")
        if self.status not in GOAL_STATUSES:
            raise ValueError(f"unknown goal status {self.status!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "progress": list(self.progress),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Goal:
        return cls(
            id=str(data["id"]),
            description=str(data["description"]),
            status=str(data.get("status", "active")),
            progress=[dict(p) for p in data.get("progress", [])],  # type: ignore[arg-type]
            created_at=str(data.get("created_at", _now_iso())),
            updated_at=str(data.get("updated_at", _now_iso())),
        )

    def context_line(self) -> str:
        """The §41 context contribution of this goal (one line)."""
        return f"- [{self.status}] {self.id}: {self.description}"


class GoalStore:
    """The durable goal ledger (Plan §7.4 pattern)."""

    def __init__(self, data_dir: str | Path) -> None:
        self._path = Path(data_dir) / "harness" / "goals.json"
        self._goals: dict[str, Goal] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    # ---------------------------------------------------------- persistence

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for item in raw.get("goals", []):
                goal = Goal.from_dict(item)
                self._goals[goal.id] = goal
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("goal ledger unreadable (%s) — reset to empty", exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"goals": [g.to_dict() for g in self._goals.values()]}
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ---------------------------------------------------------------- CRUD

    def create(self, goal_id: str, description: str, *,
               status: str = "active") -> Goal:
        goal = Goal(id=goal_id, description=description, status=status)
        self._goals[goal.id] = goal
        self._save()
        return goal

    def get(self, goal_id: str) -> Goal | None:
        return self._goals.get(goal_id)

    def list(self) -> list[Goal]:
        return [self._goals[key] for key in sorted(self._goals)]

    def active(self) -> list[Goal]:
        return [g for g in self.list() if g.status == "active"]

    def set_status(self, goal_id: str, status: str) -> Goal:
        if status not in GOAL_STATUSES:
            raise ValueError(f"unknown goal status {status!r}")
        goal = self.get(goal_id)
        if goal is None:
            raise KeyError(f"unknown goal {goal_id!r}")
        goal.status = status
        goal.updated_at = _now_iso()
        self._save()
        return goal

    def record_progress(self, goal_id: str, note: str) -> Goal:
        goal = self.get(goal_id)
        if goal is None:
            raise KeyError(f"unknown goal {goal_id!r}")
        goal.progress.append({"at": _now_iso(), "note": note})
        goal.updated_at = _now_iso()
        self._save()
        return goal

    def remove(self, goal_id: str) -> bool:
        existed = self._goals.pop(goal_id, None) is not None
        if existed:
            self._save()
        return existed

    # ------------------------------------------------------------- context

    def context_section(self, *, limit: int = 8) -> str:
        """Active goals as a context section (empty when none — quiet)."""
        goals = self.active()[: max(0, limit)]
        if not goals:
            return ""
        lines = ["PERSISTENT GOALS (outlive this task)"]
        lines.extend(goal.context_line() for goal in goals)
        return "\n".join(lines)


@dataclass(slots=True)
class Heartbeat:
    """The last-beat ledger (Plan §7.4 pattern; system lands in §23).

    ``record`` stamps an agent's beat; ``stalled`` answers whether no
    beat arrived within the interval. Beats are in-memory — a stall
    across a reboot is the Recovery phase's question, not the
    harness's.
    """

    interval_seconds: float = 30.0
    beats: dict[str, datetime] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

    def record(self, agent_id: str, *, at: datetime | None = None) -> datetime:
        stamp = at or datetime.now(UTC)
        self.beats[agent_id] = stamp
        return stamp

    def last(self, agent_id: str) -> datetime | None:
        return self.beats.get(agent_id)

    def stalled(self, agent_id: str, *, now: datetime | None = None) -> bool | None:
        """``None`` when the agent never beat (unknown ≠ stalled)."""
        stamp = self.beats.get(agent_id)
        if stamp is None:
            return None
        moment = now or datetime.now(UTC)
        return (moment - stamp) > timedelta(seconds=self.interval_seconds)

    def prune(self, agent_ids: list[str]) -> None:
        """Drop beats of agents that left the roster."""
        self.beats = {k: v for k, v in self.beats.items() if k in agent_ids}
