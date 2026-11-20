"""Audit (New Plan §21.8 · Spec §164–§165).

Spec §164's five fields, verbatim and in order::

    Who | What | When | Where | Result

and Spec §165's distinction, kept structurally: **Activity** is what
the user sees (friendly), **Audit** is the technical log for
restoration, verification and diagnosis.  Two records, two objects,
never one blurred surface.

The §21.10 tie-in is structural, not disciplinary: an
:class:`AuditLog` optionally carries a *guard* callable, and every
record's free-text fields pass through it at append time — a secret
cannot sit in the audit file even if a caller forgets to redact
(the live proof plants one and the file comes out clean).

The log is append-only in memory and writes JSONL artifacts on disk
(one JSON object per line — the house artifact format).

سجل التدقيق — خمسة حقول حرفية لكل حدث، وسجل النشاط سجلٌّ آخر منفصل
للمستخدم، والبوابة الحارسة على باب التدقيق نفسه.

Stdlib only.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import GateDecision, utc_now_iso

#: Spec §164 — the five audit fields, verbatim and in order.
AUDIT_FIELDS: tuple[str, ...] = ("who", "what", "when", "where", "result")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One audited event — the five §164 fields verbatim (+ id/detail)."""

    who: str
    what: str
    where: str
    result: str
    when: str = field(default_factory=utc_now_iso)
    detail: str = ""
    id: str = field(default_factory=lambda: f"aud_{uuid.uuid4().hex[:12]}")

    def __post_init__(self) -> None:
        if not self.who or not self.what:
            raise ValueError("audit record needs who and what")

    def as_dict(self) -> dict[str, str]:
        """The five §164 fields first (in order), then id + detail."""
        return {
            "who": self.who,
            "what": self.what,
            "when": self.when,
            "where": self.where,
            "result": self.result,
            "id": self.id,
            "detail": self.detail,
        }

    @classmethod
    def from_decision(cls, decision: GateDecision) -> AuditRecord:
        """A gate decision *is* an audit record — mapped field by field."""
        return cls(
            who=decision.action.actor,
            what=f"{decision.action.kind}:{decision.action.name}"
            + (f" → {decision.action.target}" if decision.action.target else ""),
            where=decision.action.target or decision.action.task_id or "local",
            result=decision.verdict.value,
            detail=f"gate={decision.gate} rule={decision.rule} "
            f"risk={decision.risk.value} reason={decision.reason}",
            when=decision.timestamp,
        )


class AuditLog:
    """The §164 technical log — append-only, guarded, JSONL-capable."""

    def __init__(self, guard: Callable[[str], str] | None = None) -> None:
        self._guard = guard
        self._lock = threading.Lock()
        self._records: list[AuditRecord] = []

    # ----------------------------------------------------------------- API

    def append(self, record: AuditRecord) -> AuditRecord:
        """Append one record — free-text fields pass the §21.10 guard."""
        if self._guard is not None:
            record = AuditRecord(
                who=record.who,
                what=self._guard(record.what),
                where=self._guard(record.where),
                result=record.result,
                when=record.when,
                detail=self._guard(record.detail),
                id=record.id,
            )
        with self._lock:
            self._records.append(record)
        return record

    def record_decision(self, decision: GateDecision) -> AuditRecord:
        """Append a gate decision as its §164 record."""
        return self.append(AuditRecord.from_decision(decision))

    def history(self) -> tuple[AuditRecord, ...]:
        """Every record, in append order."""
        with self._lock:
            return tuple(self._records)

    def filter(
        self,
        *,
        who: str | None = None,
        what_contains: str | None = None,
        result: str | None = None,
    ) -> tuple[AuditRecord, ...]:
        """Filter the history (case-insensitive, all criteria optional)."""
        lowered_who = (who or "").lower()
        lowered_what = (what_contains or "").lower()
        with self._lock:
            matched = [
                r for r in self._records
                if (not lowered_who or lowered_who in r.who.lower())
                and (not lowered_what or lowered_what in r.what.lower())
                and (not result or result == r.result)
            ]
        return tuple(matched)

    def size(self) -> int:
        with self._lock:
            return len(self._records)

    # ------------------------------------------------------------ artifacts

    def write_jsonl(self, path: Path | str) -> Path:
        """Write the history as JSONL (one record per line, guarded
        already at append time) — the on-disk audit artifact."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            lines = [
                json.dumps(r.as_dict(), ensure_ascii=False)
                for r in self._records
            ]
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return target

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


class ActivityFeed:
    """The §165 friendly view — what the user sees, guarded the same way."""

    def __init__(self, guard: Callable[[str], str] | None = None) -> None:
        self._guard = guard
        self._items: list[str] = []
        self._lock = threading.Lock()

    def post(self, message: str) -> str:
        """Post one friendly activity line (guarded at the door)."""
        clean = self._guard(message) if self._guard is not None else message
        with self._lock:
            self._items.append(clean)
        return clean

    def items(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._items)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def make_audit_log(guard: Callable[[str], str] | None = None) -> AuditLog:
    """The house audit log (pass the §21.10 rules guard for logs)."""
    return AuditLog(guard=guard)


def make_activity_feed(guard: Callable[[str], str] | None = None) -> ActivityFeed:
    """The house activity feed (pass the §21.10 rules guard for activity)."""
    return ActivityFeed(guard=guard)


def co_audit(
    records: Iterable[AuditRecord],
) -> list[dict[str, str]]:
    """Records → their JSON-safe dicts (convenience for writers)."""
    return [r.as_dict() for r in records]


__all__ = [
    "AUDIT_FIELDS",
    "ActivityFeed",
    "AuditLog",
    "AuditRecord",
    "GateDecision",
    "co_audit",
    "make_activity_feed",
    "make_audit_log",
]
