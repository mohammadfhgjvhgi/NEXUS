"""Agent Communication (Final Build Plan §6.5).

The structured message fields, verbatim from the plan::

    task_id
    sender
    receiver
    type
    status
    data
    evidence
    confidence

Shapes NEXUS owns on top of the verbatim fields:

* :class:`MessageType` — the closed vocabulary the runtime routes on:
  ``task`` (delegation / work assignment), ``progress``, ``result``,
  ``question``, ``coordination`` (§6.6 ownership negotiation) and
  ``error``;
* :class:`MessageStatus` — delivery lifecycle: ``sent`` →
  ``delivered`` (routed to the receiver's mailbox) → ``read`` (drained
  by the receiver);
* :class:`Evidence` — one verifiable artifact a message may carry
  (kind / source / detail — tool outputs, file references, metrics);
* ``confidence`` — clamped to ``0.0..1.0``; an honest default of 0.5,
  never an invented number.

:class:`AgentCommunicator` is the NEXUS-owned routing hub: mailboxes
per agent id, a structured per-task log, and — when enabled — an
append-only JSONL transcript under ``tasks/<task_id>.messages.jsonl``
(next to the task record, §2.5/§2.6 layout). The communicator is
single-threaded by design (Phase 1 note: only the Event Bus is
thread-safe); the loop and the master drive it synchronously.

No new event names: message routing is bookkeeping, not an event —
the §2.2 registry (28 canonical events) stays authoritative.

تواصل الوكلاء — الحقول الثمانية حرفيًا؛ صناديق بريد لكل وكيل وسجل
مُهيكل لكل مهمة مع ترانسكربت JSONL اختياري بجوار سجل المهمة.

Messaging-semantics reference: autogen-core's topic routing and
envelope design (studied in vendor-staging,
Repository-Integration Round 2, MODE D — zero imports, patterns only).

Stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger("nexus.agents")

#: The §6.5 message fields, verbatim and in plan order.
AGENT_MESSAGE_FIELDS: tuple[str, ...] = (
    "task_id",
    "sender",
    "receiver",
    "type",
    "status",
    "data",
    "evidence",
    "confidence",
)

#: Broadcast receiver sentinel (delivers to every known mailbox).
BROADCAST_RECEIVER = "*"


class MessageType:
    """Closed message-type vocabulary (documented decision)."""

    TASK = "task"
    PROGRESS = "progress"
    RESULT = "result"
    QUESTION = "question"
    COORDINATION = "coordination"
    ERROR = "error"


MESSAGE_TYPES: tuple[str, ...] = (
    MessageType.TASK,
    MessageType.PROGRESS,
    MessageType.RESULT,
    MessageType.QUESTION,
    MessageType.COORDINATION,
    MessageType.ERROR,
)


class MessageStatus:
    """Delivery lifecycle values (documented decision)."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class CommunicationError(Exception):
    """Invalid message or communicator misuse."""


# ----------------------------------------------------------------- evidence


@dataclass(frozen=True, slots=True)
class Evidence:
    """One verifiable artifact attached to a message (§6.5 evidence)."""

    kind: str      # "tool_output" | "file" | "observation" | "metric" | …
    source: str    # where it came from (tool name, path, agent id…)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "source": self.source, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Evidence:
        return cls(
            kind=str(data.get("kind", "")),
            source=str(data.get("source", "")),
            detail=str(data.get("detail", "")),
        )


# ------------------------------------------------------------------ message


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """One structured inter-agent message — the eight §6.5 fields.

    ``sequence`` / ``timestamp`` are bookkeeping assigned by the
    communicator on send (not §6.5 fields — kept out of the field
    tuple the harness proves verbatim).
    """

    task_id: str
    sender: str
    receiver: str
    type: str
    status: str = MessageStatus.SENT
    data: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()
    confidence: float = 0.5
    sequence: int = 0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise CommunicationError("message task_id must be non-empty")
        if not self.sender.strip() or not self.receiver.strip():
            raise CommunicationError("message sender/receiver must be non-empty")
        if self.type not in MESSAGE_TYPES:
            raise CommunicationError(
                f"message type must be one of {MESSAGE_TYPES}, got {self.type!r}"
            )
        if self.status not in (MessageStatus.SENT, MessageStatus.DELIVERED, MessageStatus.READ):
            raise CommunicationError(f"invalid message status {self.status!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise CommunicationError(
                f"confidence must be within 0.0..1.0, got {self.confidence}"
            )

    # -------------------------------------------------------- derived

    def with_status(self, status: str, *, sequence: int | None = None) -> AgentMessage:
        """Copy with a new delivery status (immutable record)."""
        return replace(
            self,
            status=status,
            sequence=sequence if sequence is not None else self.sequence,
        )

    # ---------------------------------------------------- round-trips

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "type": self.type,
            "status": self.status,
            "data": dict(self.data),
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
        }

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        sender: str,
        receiver: str,
        type: str,  # noqa: A002 — §6.5 field name is the plan's own
        data: Mapping[str, Any] | None = None,
        evidence: Sequence[Evidence] = (),
        confidence: float = 0.5,
    ) -> AgentMessage:
        """Validating factory (status starts at ``sent``)."""
        return cls(
            task_id=task_id,
            sender=sender,
            receiver=receiver,
            type=type,
            status=MessageStatus.SENT,
            data=dict(data or {}),
            evidence=tuple(evidence),
            confidence=confidence,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AgentMessage:
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise CommunicationError(f"unknown message fields: {sorted(unknown)}")
        return cls(
            task_id=str(data["task_id"]),
            sender=str(data["sender"]),
            receiver=str(data["receiver"]),
            type=str(data["type"]),
            status=str(data.get("status", MessageStatus.SENT)),
            data=dict(data.get("data") or {}),
            evidence=tuple(
                Evidence.from_dict(item) for item in data.get("evidence") or ()
            ),
            confidence=float(data.get("confidence", 0.5)),
            sequence=int(data.get("sequence", 0)),
            timestamp=str(data.get("timestamp", "")),
        )


# ------------------------------------------------------------- communicator


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class AgentCommunicator:
    """The routing hub — mailboxes, structured log, JSONL transcript.

    ``send`` routes one message: the log keeps the ``sent`` record, the
    receiver's mailbox (or every mailbox, for the ``*`` broadcast
    sentinel) receives a ``delivered`` copy. ``receive`` drains a
    mailbox and marks the copies ``read``. The log is the queryable
    §6.5 record; the optional transcript survives reboots.
    """

    def __init__(self, tasks_dir: str | Path | None = None, *, persist: bool = True) -> None:
        self._tasks_dir = Path(tasks_dir) if tasks_dir is not None else None
        self._persist = persist and self._tasks_dir is not None
        self._mailboxes: dict[str, deque[AgentMessage]] = {}
        self._log: list[AgentMessage] = []
        self._sequence = 0

    # ---------------------------------------------------------------- send

    def send(self, message: AgentMessage) -> AgentMessage:
        """Route one message; returns the delivered record."""
        if message.status != MessageStatus.SENT:
            raise CommunicationError("send expects a message in 'sent' status")
        self._sequence += 1
        stamped = replace(
            message,
            sequence=self._sequence,
            timestamp=_utc_now_iso(),
        )
        self._log.append(stamped)
        if self._persist:
            self._append_transcript(stamped)
        delivered = stamped.with_status(MessageStatus.DELIVERED)
        receivers = (
            sorted(self._mailboxes)
            if message.receiver == BROADCAST_RECEIVER
            else [message.receiver]
        )
        for receiver in receivers:
            self._mailboxes.setdefault(receiver, deque()).append(delivered)
        return delivered

    # ------------------------------------------------------------- receive

    def receive(
        self, agent_id: str, *, limit: int | None = None
    ) -> tuple[AgentMessage, ...]:
        """Drain one agent's mailbox; the copies become ``read``."""
        box = self._mailboxes.get(agent_id)
        if not box:
            return ()
        count = len(box) if limit is None else min(limit, len(box))
        drained: list[AgentMessage] = []
        for _ in range(count):
            message = box.popleft()
            read = message.with_status(MessageStatus.READ)
            self._log_replace(message, read)
            drained.append(read)
        return tuple(drained)

    def peek(self, agent_id: str) -> tuple[AgentMessage, ...]:
        """Inspect a mailbox without draining it."""
        box = self._mailboxes.get(agent_id)
        return tuple(box) if box else ()

    def mailbox_size(self, agent_id: str) -> int:
        box = self._mailboxes.get(agent_id)
        return len(box) if box else 0

    # ----------------------------------------------------------------- log

    def log(self, task_id: str | None = None) -> tuple[AgentMessage, ...]:
        """The structured message record (optionally per task)."""
        if task_id is None:
            return tuple(self._log)
        return tuple(m for m in self._log if m.task_id == task_id)

    def message_count(self) -> int:
        return len(self._log)

    def last(self, task_id: str | None = None) -> AgentMessage | None:
        records = self.log(task_id)
        return records[-1] if records else None

    # ---------------------------------------------------------- internals

    def _log_replace(self, old: AgentMessage, new: AgentMessage) -> None:
        """Replace the log record carrying the same sequence (the log
        keeps the stamped 'sent' record; mailbox copies share its
        sequence — matching by identity would never hit)."""
        for index, message in enumerate(self._log):
            if message.sequence == old.sequence:
                self._log[index] = new
                return

    def _append_transcript(self, message: AgentMessage) -> None:
        assert self._tasks_dir is not None
        path = self._transcript_path(message.task_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            # The transcript is a durability aid, never a blocker.
            logger.warning("message transcript append failed: %s", exc)

    def _transcript_path(self, task_id: str) -> Path:
        assert self._tasks_dir is not None
        return self._tasks_dir / f"{task_id}.messages.jsonl"
