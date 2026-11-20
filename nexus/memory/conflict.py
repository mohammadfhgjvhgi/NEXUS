"""Memory conflict resolution (New Plan §12.8 / Build Plan §13.7).

The ladder, verbatim — *current prompt wins, then everything older
and broader loses in order*::

    Current prompt        (highest — the §13.7 «الجديد يفوز» rule,
                           encoded as recency inside the same level)
    >
    Current task          (TASK · SESSION scopes)
    >
    Workspace rules       (WORKSPACE scope, RULE/DECISION types)
    >
    Project decisions     (PROJECT scope)
    >
    User preferences      (USER scope, PREFERENCE type)
    >
    Old lessons           (LESSON — the lowest)

Two records *conflict* when they share a ``conflict_key`` (the writer
declares the family: "preferred-model", "project-layout"…). The
resolver picks one winner per family —
``(priority rank, updated_at, id)`` descending — and documents the
losers. Losers are **not** forgotten: they stay in the store (§12.9 is
the only path that removes memory); they just do not enter the
assembled context.

حلّ تعارض الذاكرة — سُلّم الأولويات حرفيًا؛ الخاسر يبقى في
المخزن ولا يدخل السياق فقط.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .contracts import (
    MemoryRecord,
    MemoryScope,
    MemoryType,
)

#: §12.8 verbatim — the six levels, highest first.
CONFLICT_PRIORITY: tuple[str, ...] = (
    "current_prompt",
    "current_task",
    "workspace_rules",
    "project_decisions",
    "user_preferences",
    "old_lessons",
)

#: Rank per level (lower number = stronger).
_LEVEL_RANK: dict[str, int] = {
    level: rank for rank, level in enumerate(CONFLICT_PRIORITY)
}


def conflict_level(record: MemoryRecord) -> str:
    """Map a record onto its §12.8 ladder level."""
    if record.scope in (MemoryScope.TASK, MemoryScope.SESSION):
        return "current_task"
    if record.scope == MemoryScope.WORKSPACE:
        if record.type in (MemoryType.RULE, MemoryType.DECISION):
            return "workspace_rules"
        return "current_task"
    if record.scope == MemoryScope.PROJECT:
        return "project_decisions"
    if record.scope == MemoryScope.USER:
        if record.type == MemoryType.PREFERENCE:
            return "user_preferences"
        return "current_task"
    # semantic scopes
    if record.scope == MemoryScope.LESSON:
        return "old_lessons"
    if record.type == MemoryType.RULE and record.scope == MemoryScope.KNOWLEDGE:
        return "workspace_rules"
    if record.type == MemoryType.DECISION:
        return "project_decisions"
    if record.type == MemoryType.PREFERENCE:
        return "user_preferences"
    if record.type == MemoryType.LESSON:
        return "old_lessons"
    return "current_task"


def _parse_ts(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=UTC)


@dataclass(slots=True)
class ConflictOutcome:
    """One resolved conflict family (§12.8 documentation unit)."""

    conflict_key: str
    winner: MemoryRecord
    losers: list[MemoryRecord] = field(default_factory=list)

    @property
    def level(self) -> str:
        return conflict_level(self.winner)

    def describe(self) -> str:
        loser_ids = ", ".join(record.id for record in self.losers) or "—"
        return (
            f"conflict[{self.conflict_key}] winner={self.winner.id} "
            f"level={self.level} superseded=[{loser_ids}]"
        )


class ConflictResolver:
    """Group by conflict_key → pick the winner by the §12.8 ladder."""

    def resolve(
        self, records: list[MemoryRecord]
    ) -> tuple[list[MemoryRecord], list[ConflictOutcome]]:
        """Returns (kept winners, conflict notes) for the ranked input.

        Records without a conflict_key pass through untouched. Inside a
        family the winner is ``(level rank, updated_at, id)`` maximal —
        the recency term is the §13.7 «the new instruction wins» rule
        made arithmetic.
        """
        families: dict[str, list[MemoryRecord]] = {}
        ordered: list[MemoryRecord] = []
        for record in records:
            if record.conflict_key:
                families.setdefault(record.conflict_key, []).append(record)
            else:
                ordered.append(record)
        notes: list[ConflictOutcome] = []
        for key in sorted(families):
            family = families[key]
            if len(family) < 2:
                # a single record with a conflict_key is a family of
                # one — no conflict to resolve, no note (notes are for
                # real disagreements the context must know about)
                ordered.append(family[0])
                continue
            winner = max(
                family,
                key=lambda record: (
                    -_LEVEL_RANK[conflict_level(record)],
                    _parse_ts(record.updated_at),
                    record.id,
                ),
            )
            losers = [record for record in family if record.id != winner.id]
            ordered.append(winner)
            notes.append(
                ConflictOutcome(conflict_key=key, winner=winner, losers=losers)
            )
        return ordered, notes
