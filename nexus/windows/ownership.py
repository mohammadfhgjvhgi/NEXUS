"""Window Ownership (Final Build Plan §10.2 — Spec §61).

The human-parallelism primitive: every window's *input* belongs to
someone — ``USER`` · ``NEXUS`` · ``SHARED``. Ownership is decided by
an ordered rule list (process / title patterns) plus explicit
assignments, with the safe default **USER** (an unclaimed window is
the human's — NEXUS never assumes control it was not given).

The spec's own example (§61) is seeded as the demo ruleset:

=================  =========
War Thunder       USER
Chrome A          USER
Chrome B          NEXUS
PowerPoint        NEXUS
=================  =========

Chrome A vs. B shows why *two* rule kinds exist: same process,
different windows — the split is by title. Rules are data, not code:
the operator rewrites them per task.

ملكية النافذة — قواعد مرتّبة وتخصيصات صريحة، والافتراض الآمن
هو USER: ما لم يُصرَّح به فهو للمستخدم.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .registry import WindowRecord

OWNERS: tuple[str, ...] = ("USER", "NEXUS", "SHARED")


class InputOwner:  # noqa: N801 — a plain string namespace on purpose
    """The §62 three-way vocabulary (records and rules share it)."""

    USER = "USER"
    NEXUS = "NEXUS"
    SHARED = "SHARED"


@dataclass(frozen=True, slots=True)
class OwnershipRule:
    """One pattern → owner decision, with priority (higher wins)."""

    kind: str  # "process" | "title" — case-insensitive substring match
    pattern: str
    owner: str  # InputOwner.*
    priority: int = 0
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("process", "title"):
            raise ValueError(f"rule kind must be process|title, got {self.kind!r}")
        if self.owner not in OWNERS:
            raise ValueError(f"rule owner must be {OWNERS}, got {self.owner!r}")
        if not self.pattern:
            raise ValueError("rule pattern must be non-empty")


#: The §10.2 demo ruleset — Spec §61, verbatim intent. Chrome A/B is
#: one process split by title; replace per task (rules are data).
DEMO_RULES: tuple[OwnershipRule, ...] = (
    OwnershipRule(
        kind="title", pattern="war thunder", owner=InputOwner.USER,
        priority=100, description="Spec §61: War Thunder → USER",
    ),
    OwnershipRule(
        kind="title", pattern="nexus", owner=InputOwner.NEXUS,
        priority=60, description="Spec §61: Chrome B → NEXUS (title-tagged)",
    ),
    OwnershipRule(
        kind="title", pattern="youtube", owner=InputOwner.USER,
        priority=50, description="Spec §61: Chrome A → USER (the human's tab)",
    ),
    OwnershipRule(
        kind="process", pattern="powerpnt", owner=InputOwner.NEXUS,
        priority=50, description="Spec §61: PowerPoint → NEXUS",
    ),
    OwnershipRule(
        kind="process", pattern="code", owner=InputOwner.NEXUS,
        priority=40, description="Spec §61: VS Code → NEXUS",
    ),
)


@dataclass(slots=True)
class OwnershipPolicy:
    """Rules + assignments → the owner of every record.

    * ``rules`` — the ordered pattern list (Spec §61 semantics);
    * ``assignments`` — explicit per-window_id claims (a task staking
      a window); an assignment always beats pattern rules;
    * ``default_owner`` — what an unmatched window gets. **USER**:
      the safe default. NEXUS never assumes input it was not given.
    """

    rules: list[OwnershipRule] = field(default_factory=lambda: list(DEMO_RULES))
    assignments: dict[str, str] = field(default_factory=dict)
    default_owner: str = InputOwner.USER

    def __post_init__(self) -> None:
        if self.default_owner not in OWNERS:
            raise ValueError(
                f"default_owner must be {OWNERS}, got {self.default_owner!r}"
            )

    # ------------------------------------------------------------ decide

    def resolve(self, record: WindowRecord) -> str:
        """The owner of one record: assignment → best rule → default."""
        assigned = self.assignments.get(record.window_id)
        if assigned is not None:
            return assigned
        best = self._best_rule(record)
        return best.owner if best is not None else self.default_owner

    def _best_rule(self, record: WindowRecord) -> OwnershipRule | None:
        candidates = [rule for rule in self.rules if self._matches(rule, record)]
        if not candidates:
            return None
        # highest priority wins; ties keep declaration order (stable max).
        best = candidates[0]
        for rule in candidates[1:]:
            if rule.priority > best.priority:
                best = rule
        return best

    @staticmethod
    def _matches(rule: OwnershipRule, record: WindowRecord) -> bool:
        haystack = record.application if rule.kind == "process" else record.title
        return rule.pattern.lower() in haystack.lower()

    # ------------------------------------------------------------ mutate

    def assign(self, window_id: str, owner: str) -> None:
        """Explicit claim — beats every rule for this window."""
        if owner not in OWNERS:
            raise ValueError(f"owner must be {OWNERS}, got {owner!r}")
        self.assignments[window_id] = owner

    def release(self, window_id: str) -> bool:
        return self.assignments.pop(window_id, None) is not None

    def add_rule(self, rule: OwnershipRule) -> None:
        self.rules.append(rule)

    # ------------------------------------------------------------- apply

    def apply(self, records: Iterable[WindowRecord]) -> list[WindowRecord]:
        """Return the records with ``input_owner`` resolved (pure)."""
        return [
            replace(record, input_owner=self.resolve(record))
            for record in records
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "rules": [
                {
                    "kind": rule.kind,
                    "pattern": rule.pattern,
                    "owner": rule.owner,
                    "priority": rule.priority,
                    "description": rule.description,
                }
                for rule in self.rules
            ],
            "assignments": dict(self.assignments),
            "default_owner": self.default_owner,
        }


def parse_rules(rows: Iterable[Mapping[str, Any]]) -> list[OwnershipRule]:
    """Build rules from mapping rows (config/JSON shape)."""
    return [
        OwnershipRule(
            kind=str(row["kind"]),
            pattern=str(row["pattern"]),
            owner=str(row["owner"]),
            priority=int(row.get("priority", 0)),
            description=str(row.get("description", "")),
        )
        for row in rows
    ]


__all__ = [
    "DEMO_RULES",
    "InputOwner",
    "OWNERS",
    "OwnershipPolicy",
    "OwnershipRule",
    "parse_rules",
]
