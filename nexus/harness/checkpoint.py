"""Checkpoint store (Plan §7.3 — the LangGraph checkpoint/durability pattern).

LangGraph's checkpoint layer saves graph state at supersteps and lets
an execution resume from the last saved state, with explicit
durability modes. NEXUS adapts the *pattern* over the §2.4 task
machine:

* :class:`Durability` — ``NONE`` (no checkpoints, zero cost),
  ``MEMORY`` (this process only), ``DISK`` (atomic JSONL append +
  reload on boot — the long-running default);
* :class:`Checkpoint` — a task/agent state snapshot with a reason;
* :class:`CheckpointStore` — save / latest / list / resume, bounded by
  a retention window (per task), pruning the oldest on overflow.

Two integration seams:

* **explicit** — ``save(task, state, reason)`` from any caller;
* **event-driven** — ``bind_bus`` subscribes to the §2.2 task
  lifecycle events (started/paused/resumed/completed) and snapshots
  the task state on every transition, publishing the canonical
  ``checkpoint.created`` event (already in the 28 — the name guard
  stays binding; no new names).

``resume`` returns the last checkpoint's state dict — the caller (a
§6.3 master continuation, a later-phase recovery engine) decides what
to do with it. This module never imports LangGraph.

Stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..events import Event, EventBus, EventName

logger = logging.getLogger("nexus.harness")

#: The §7.3 checkpoint record fields (harness-provable).
CHECKPOINT_FIELDS: tuple[str, ...] = (
    "id",
    "task_id",
    "agent_id",
    "state",
    "reason",
    "created_at",
)

#: Events that trigger an automatic checkpoint when bound to the bus.
_AUTO_EVENTS: tuple[EventName, ...] = (
    EventName.TASK_STARTED,
    EventName.TASK_PAUSED,
    EventName.TASK_RESUMED,
    EventName.TASK_COMPLETED,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Durability(StrEnum):
    """When checkpoints persist (the LangGraph durability vocabulary)."""

    NONE = "none"
    MEMORY = "memory"
    DISK = "disk"


@dataclass(slots=True)
class Checkpoint:
    """One durable state snapshot (LangGraph pattern, NEXUS-owned)."""

    id: str
    task_id: str
    agent_id: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    created_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("checkpoint.id must be non-empty")
        if not self.task_id:
            raise ValueError("checkpoint.task_id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "state": dict(self.state),
            "reason": self.reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Checkpoint:
        return cls(
            id=str(data["id"]),
            task_id=str(data["task_id"]),
            agent_id=str(data.get("agent_id", "")),
            state=dict(data.get("state") or {}),
            reason=str(data.get("reason", "")),
            created_at=str(data.get("created_at", _now_iso())),
        )


class CheckpointStore:
    """The checkpoint ledger (Plan §7.3 pattern).

    DISK mode appends one JSON object per line under
    ``<root>/checkpoints.jsonl`` (``NexusPaths.checkpoints``) with the
    project's atomic-write discipline; MEMORY keeps an in-process
    deque per task; NONE keeps nothing (every call is a no-op that
    honestly reports emptiness).
    """

    def __init__(
        self,
        root: str | Path,
        *,
        mode: Durability = Durability.DISK,
        retention: int = 64,
        bus: EventBus | None = None,
    ) -> None:
        if retention < 1:
            raise ValueError(f"retention must be >= 1, got {retention}")
        self._path = Path(root) / "checkpoints.jsonl"
        self._mode = mode
        self._retention = retention
        self._memory: dict[str, list[Checkpoint]] = {}
        self._counter = 0
        self._bound_bus: EventBus | None = None
        if mode is Durability.DISK:
            self._reload()
        if bus is not None:
            self.bind_bus(bus)

    # ------------------------------------------------------------ plumbing

    @property
    def mode(self) -> Durability:
        return self._mode

    @property
    def path(self) -> Path:
        return self._path

    def _reload(self) -> None:
        if not self._path.is_file():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("checkpoint ledger unreadable (%s) — reset", exc)
            return
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                checkpoint = Checkpoint.from_dict(json.loads(line))
            except (ValueError, KeyError, TypeError):
                continue  # a torn line never kills the boot
            self._memory.setdefault(checkpoint.task_id, []).append(checkpoint)
            try:
                numeric = int(checkpoint.id.rsplit("-", 1)[-1])
                self._counter = max(self._counter, numeric)
            except ValueError:
                continue

    def _append_disk(self, checkpoint: Checkpoint) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(checkpoint.to_dict(), ensure_ascii=False)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                if self._path.exists():
                    handle.write(self._path.read_text(encoding="utf-8"))
                handle.write(line + "\n")
            os.replace(tmp, self._path)
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _prune(self, task_id: str) -> None:
        entries = self._memory.get(task_id, [])
        while len(entries) > self._retention:
            dropped = entries.pop(0)
            logger.debug("checkpoint %s pruned (retention=%d)", dropped.id, self._retention)

    def _rewrite_disk(self, task_id: str) -> None:
        """Serialize the pruned window (per-task retention is honest)."""
        keep: list[Checkpoint] = []
        for tid in sorted(self._memory):
            keep.extend(self._memory[tid][-self._retention :])
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for checkpoint in keep:
                    handle.write(
                        json.dumps(checkpoint.to_dict(), ensure_ascii=False) + "\n"
                    )
            os.replace(tmp, self._path)
        except OSError:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ---------------------------------------------------------------- save

    def save(
        self,
        task_id: str,
        state: Mapping[str, Any],
        *,
        agent_id: str = "",
        reason: str = "",
        checkpoint_id: str | None = None,
    ) -> Checkpoint | None:
        """Snapshot one state (returns None in NONE mode — honest)."""
        if self._mode is Durability.NONE:
            return None
        self._counter += 1
        checkpoint = Checkpoint(
            id=checkpoint_id or f"cp-{task_id}-{self._counter:06d}",
            task_id=task_id,
            agent_id=agent_id,
            state=dict(state),
            reason=reason,
        )
        self._memory.setdefault(task_id, []).append(checkpoint)
        self._prune(task_id)
        if self._mode is Durability.DISK:
            self._rewrite_disk(task_id)
        if self._bound_bus is not None:
            self._bound_bus.publish(
                EventName.CHECKPOINT_CREATED,
                payload={
                    "checkpoint_id": checkpoint.id,
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "reason": reason,
                },
                source="nexus.harness.checkpoint",
                task_id=task_id,
            )
        return checkpoint

    # ------------------------------------------------------------- queries

    def latest(self, task_id: str) -> Checkpoint | None:
        entries = self._memory.get(task_id, [])
        return entries[-1] if entries else None

    def list(self, task_id: str) -> list[Checkpoint]:
        return list(self._memory.get(task_id, ()))

    def count(self, task_id: str | None = None) -> int:
        if task_id is None:
            return sum(len(v) for v in self._memory.values())
        return len(self._memory.get(task_id, ()))

    # --------------------------------------------------------------- resume

    def resume(self, task_id: str) -> dict[str, Any] | None:
        """The state dict of the latest checkpoint (None → cold start)."""
        checkpoint = self.latest(task_id)
        if checkpoint is None:
            return None
        return dict(checkpoint.state)

    # ------------------------------------------------------------- binding

    def bind_bus(self, bus: EventBus) -> None:
        """Auto-checkpoint every task lifecycle transition (§2.2 names).

        The snapshot payload carries the event payload verbatim; the
        canonical ``checkpoint.created`` publication keeps the 28-event
        registry authoritative.
        """
        if self._bound_bus is bus:
            return

        def handler(event: Event) -> None:
            self.save(
                str(event.task_id or ""),
                {"event": event.name, "payload": dict(event.payload)},
                agent_id=str(event.payload.get("agent_id", "")),
                reason=f"bus:{event.name}",
            )

        for event in _AUTO_EVENTS:
            bus.subscribe(event.value, handler)
        self._bound_bus = bus
