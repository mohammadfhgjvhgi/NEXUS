"""Learning contracts (New Plan §13.1 / §13.2 / §13.4).

The phase thesis — the plan says it best::

    التمييز بين «يتذكر» و«يتعلم»
    (telling "it remembers" from "it learns")

§13.1 fixes the six experience kinds, verbatim::

    success · failure · decision · pattern · lesson · skill_candidate

§13.2 fixes the Learning Record fields, verbatim::

    experience_id · lesson · source_task · evidence · confidence · scope

§13.4 fixes the skill-candidate shape: a workflow that repeats —
Task A, Task B, Task C — folds into a pattern, and the pattern into a
skill candidate.

Architecture invariant (Plan §61, same law as PHASE 12): *NEXUS owns
Learning semantics*. These contracts are NEXUS-native; letta-code
(§13.5, MODE D), prime-agent (§13.6, MODE D/B) and DSPy (§13.7, MODE
D) were studied in ``vendor-staging/phase-13/`` and are referenced —
none of their code is imported, and nothing here depends on them.

عقود التعلّم — الأنواع الستة وسجل التعلّم ومرشّح المهارة، حرفيًا
كما في الخطة؛ النواة تملك دلالات التعلّم والمراجع الخارجية خلف
الحدود فقط.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nexus.memory.contracts import (
    MEMORY_SCOPES,
    MemoryEvidence,
)

# ----------------------------------------------------------------- errors


class LearningError(Exception):
    """Learning misuse or backend failure."""


class InvalidLearningError(LearningError):
    """An experience/record/candidate violates the §13 contract."""


# ----------------------------------------------------- §13.1 experience


class ExperienceKind:
    """The six §13.1 kinds, verbatim vocabulary."""

    SUCCESS = "success"
    FAILURE = "failure"
    DECISION = "decision"
    PATTERN = "pattern"
    LESSON = "lesson"
    SKILL_CANDIDATE = "skill_candidate"


EXPERIENCE_KINDS: tuple[str, ...] = (
    ExperienceKind.SUCCESS,
    ExperienceKind.FAILURE,
    ExperienceKind.DECISION,
    ExperienceKind.PATTERN,
    ExperienceKind.LESSON,
    ExperienceKind.SKILL_CANDIDATE,
)

#: Container fields an experience may carry (the §12.2 ladder rides in
#: on the memory vocabulary — one scope system for both engines, so a
#: lesson lands exactly where the retrieval pipeline already looks).
EXPERIENCE_CONTAINERS: tuple[str, ...] = (
    "project",
    "workspace",
    "task",
    "session",
    "agent",
)


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds (house format)."""
    return datetime.now(UTC).isoformat()


def new_learning_id(prefix: str, seed: str = "") -> str:
    """Deterministic id for tests (seeded), random otherwise.

    ``prefix`` is one of ``exp_`` / ``les_`` / ``skc_`` + 16 hex —
    short, greppable, collision-safe for the local single-writer store.
    """
    if seed:
        digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).hexdigest()
    else:
        digest = secrets.token_hex(8)
    return f"{prefix}{digest}"


@dataclass(slots=True)
class Experience:
    """One lived event — the §13.1 raw material the extractor emits.

    ``kind``        — one of the six EXPERIENCE_KINDS.
    ``task_id``     — the task that produced it.
    ``summary``     — what actually happened (one honest sentence).
    ``evidence``    — provenance captured at the moment (§12.1 shape;
                      learning reuses the memory evidence vocabulary).
    ``payload``     — the raw facts (JSON-safe) for later re-mining.
    """

    id: str
    kind: str
    task_id: str
    summary: str
    evidence: tuple[MemoryEvidence, ...] = ()
    project: str | None = None
    workspace: str | None = None
    task: str | None = None
    session: str | None = None
    agent: str | None = None
    occurred_at: str = ""
    payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not re.match(r"^exp_[0-9a-f]{16}$", self.id):
            raise InvalidLearningError(
                "experience id must be 'exp_' + 16 hex (exp_abcd0123456789ef)"
            )
        if self.kind not in EXPERIENCE_KINDS:
            raise InvalidLearningError(
                f"kind must be one of the six §13.1 kinds, got {self.kind!r}"
            )
        if not self.task_id.strip():
            raise InvalidLearningError("experience needs the task that lived it")
        if not self.summary.strip():
            raise InvalidLearningError(
                "experience summary must not be empty — an experience "
                "with no description cannot become a lesson"
            )
        if not self.occurred_at:
            self.occurred_at = utc_now_iso()
        if self.payload is None:
            self.payload = {}

    def evidence_rows(self) -> list[dict[str, str]]:
        """Evidence as plain rows (store/JSON shape)."""
        return [
            {
                "method": e.method,
                "uri": e.uri,
                "snippet": e.snippet,
                "captured_at": e.captured_at,
            }
            for e in self.evidence
        ]

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe view (audit/logging/pipeline payloads)."""
        return {
            "id": self.id,
            "kind": self.kind,
            "task_id": self.task_id,
            "summary": self.summary,
            "evidence": self.evidence_rows(),
            "project": self.project,
            "workspace": self.workspace,
            "task": self.task,
            "session": self.session,
            "agent": self.agent,
            "occurred_at": self.occurred_at,
            "payload": self.payload or {},
        }


# --------------------------------------------------- §13.2 learning record

_ID_LESSON_RE = re.compile(r"^les_[0-9a-f]{16}$")

#: §13.2 verbatim (six) + the house seams the pipeline needs.
LEARNING_RECORD_FIELDS: tuple[str, ...] = (
    "experience_id",
    "lesson",
    "source_task",
    "evidence",
    "confidence",
    "scope",
    # house seams (documented beyond §13.2)
    "id",
    "status",
    "occurrences",
    "signature",
    "memory_id",
    "created_at",
    "updated_at",
    "project",
    "workspace",
    "task",
    "session",
    "agent",
)

#: Record lifecycle: pending (stored, needs more evidence) → promoted
#: (written to the Memory Engine, retrievable in future context) →
#: superseded (a newer lesson replaced it).
LEARNING_STATUSES: tuple[str, ...] = ("pending", "promoted", "superseded")


def lesson_signature(lesson: str, scope: str) -> str:
    """Stable dedupe key — same lesson text in the same scope is the
    same lesson, whatever task re-learned it (occurrences merge)."""
    digest = hashlib.blake2b(
        f"{scope}::{lesson.strip().casefold()}".encode(),
        digest_size=8,
    ).hexdigest()
    return f"lsig_{digest}"


@dataclass(slots=True)
class LearningRecord:
    """One learned lesson — §13.2's six fields verbatim, plus seams.

    ``confidence`` — 0.05–0.95, never 1.0: a lesson is corrigible by
    design (a later contradicting lesson wins, §12.8 recency).
    ``occurrences``— how many experiences kept teaching it (merged by
    ``signature``); repetition raises confidence, §13.3 stage 4.
    ``memory_id``  — the §12 engine record once promoted, else None.
    """

    id: str
    experience_id: str
    lesson: str
    source_task: str
    evidence: tuple[MemoryEvidence, ...] = ()
    confidence: float = 0.0
    scope: str = "lesson"
    status: str = "pending"
    occurrences: int = 1
    signature: str = ""
    memory_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    project: str | None = None
    workspace: str | None = None
    task: str | None = None
    session: str | None = None
    agent: str | None = None

    def __post_init__(self) -> None:
        if not _ID_LESSON_RE.match(self.id):
            raise InvalidLearningError(
                "learning record id must be 'les_' + 16 hex"
            )
        if not self.experience_id.strip():
            raise InvalidLearningError("record needs its source experience_id")
        if not self.lesson.strip():
            raise InvalidLearningError("the lesson text must not be empty")
        if not self.source_task.strip():
            raise InvalidLearningError("the source task must be named")
        if self.scope not in MEMORY_SCOPES:
            raise InvalidLearningError(
                f"scope reuses the §12.2 twelve — got {self.scope!r}"
            )
        if self.status not in LEARNING_STATUSES:
            raise InvalidLearningError(
                f"status must be one of {LEARNING_STATUSES}, got {self.status!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidLearningError(
                f"confidence must be within [0.0, 1.0], got {self.confidence}"
            )
        if self.occurrences < 1:
            raise InvalidLearningError("occurrences must be >= 1")
        if not self.signature:
            self.signature = lesson_signature(self.lesson, self.scope)
        now = utc_now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at

    def evidence_rows(self) -> list[dict[str, str]]:
        return [
            {
                "method": e.method,
                "uri": e.uri,
                "snippet": e.snippet,
                "captured_at": e.captured_at,
            }
            for e in self.evidence
        ]

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe view (reports/pipeline payloads)."""
        return {
            "id": self.id,
            "experience_id": self.experience_id,
            "lesson": self.lesson,
            "source_task": self.source_task,
            "evidence": self.evidence_rows(),
            "confidence": self.confidence,
            "scope": self.scope,
            "status": self.status,
            "occurrences": self.occurrences,
            "signature": self.signature,
            "memory_id": self.memory_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project": self.project,
            "workspace": self.workspace,
            "task": self.task,
            "session": self.session,
            "agent": self.agent,
        }


# ------------------------------------------------- §13.4 skill candidate

_ID_SKILL_RE = re.compile(r"^skc_[0-9a-f]{16}$")

#: §13.4's own example: Task A, Task B, Task C — three repeats make a
#: candidate. Fewer is noise, not a skill.
SKILL_MIN_REPEATS = 3

SKILL_STATUSES: tuple[str, ...] = ("candidate", "promoted", "rejected")


def workflow_signature(steps: tuple[str, ...]) -> str:
    """Pattern key for a step sequence — normalized, order-kept."""
    normalized = " > ".join(s.strip().casefold() for s in steps if s.strip())
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=8).hexdigest()
    return f"wsig_{digest}"


@dataclass(slots=True)
class SkillCandidate:
    """A workflow that kept repeating — §13.4's pattern, caught.

    ``pattern``      — the workflow signature (``wsig_…``).
    ``steps``        — the actual step sequence (Task A's steps ==
                       Task B's steps modulo naming noise).
    ``occurrences``  — how many distinct tasks ran this workflow.
    ``source_tasks`` — the task ids that lived it (the evidence trail).
    """

    id: str
    pattern: str
    steps: tuple[str, ...]
    occurrences: int
    evidence: tuple[MemoryEvidence, ...] = ()
    confidence: float = 0.0
    status: str = "candidate"
    source_tasks: tuple[str, ...] = ()
    memory_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not _ID_SKILL_RE.match(self.id):
            raise InvalidLearningError(
                "skill candidate id must be 'skc_' + 16 hex"
            )
        if not self.pattern.startswith("wsig_"):
            raise InvalidLearningError(
                "pattern must be a workflow_signature (wsig_…)"
            )
        if not self.steps or any(not s.strip() for s in self.steps):
            raise InvalidLearningError(
                "a skill candidate needs a non-empty step sequence"
            )
        if self.occurrences < 1:
            raise InvalidLearningError("occurrences must be >= 1")
        if self.status not in SKILL_STATUSES:
            raise InvalidLearningError(
                f"status must be one of {SKILL_STATUSES}, got {self.status!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidLearningError(
                f"confidence must be within [0.0, 1.0], got {self.confidence}"
            )
        if not self.created_at:
            self.created_at = utc_now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def evidence_rows(self) -> list[dict[str, str]]:
        return [
            {
                "method": e.method,
                "uri": e.uri,
                "snippet": e.snippet,
                "captured_at": e.captured_at,
            }
            for e in self.evidence
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pattern": self.pattern,
            "steps": list(self.steps),
            "occurrences": self.occurrences,
            "evidence": self.evidence_rows(),
            "confidence": self.confidence,
            "status": self.status,
            "source_tasks": list(self.source_tasks),
            "memory_id": self.memory_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# -------------------------------------------- §13.3 confidence mechanics

#: Kind priors — what a fresh experience is worth before corroboration.
KIND_BASE_CONFIDENCE: dict[str, float] = {
    ExperienceKind.SUCCESS: 0.55,
    ExperienceKind.FAILURE: 0.65,
    ExperienceKind.DECISION: 0.70,
    ExperienceKind.PATTERN: 0.50,
    ExperienceKind.LESSON: 0.50,
    ExperienceKind.SKILL_CANDIDATE: 0.50,
}

#: A lesson must clear this to enter the Memory Engine (§13.3 stage 5
#: → future retrieval). At 0.65: one tool_run evidence (0.60) stays
#: pending — a lesson needs either a second capture method or a
#: repeat before it claims future context. Below it, the lesson stays
#: pending in the learning store — honest, re-minable, never silently
#: dropped.
LEARN_PROMOTE_THRESHOLD = 0.65

#: Hard caps — a lesson is always corrigible, a skill needs the repeats.
CONFIDENCE_FLOOR = 0.05
CONFIDENCE_CEILING = 0.95

#: Evidence check floor — a candidate lesson with no evidence is not
#: a lesson, it is an opinion (§13.3 stage 3 refuses it outright).
MIN_EVIDENCE_ITEMS = 1


def confidence_for(
    kind: str,
    *,
    evidence_methods: tuple[str, ...] = (),
    occurrences: int = 1,
) -> float:
    """§13.3 stage 4 — the pure confidence rule.

    kind prior + one notch per *distinct* evidence method (capped)
    + one notch per extra occurrence beyond the first (capped), then
    clamped to [0.05, 0.95] — never 1.0, learning stays corrigible.
    """
    base = KIND_BASE_CONFIDENCE.get(kind, 0.50)
    distinct = len({m for m in evidence_methods if m})
    evidence_bonus = min(0.10 * distinct, 0.25)
    repeat_bonus = min(0.08 * max(occurrences - 1, 0), 0.24)
    value = base + evidence_bonus + repeat_bonus
    return round(min(max(value, CONFIDENCE_FLOOR), CONFIDENCE_CEILING), 4)


def evidence_methods_of(items: tuple[MemoryEvidence, ...]) -> tuple[str, ...]:
    """Distinct capture methods present in an evidence tuple."""
    return tuple({e.method for e in items})


#: The kind → §12 memory type mapping the promotion writes through.
LESSON_MEMORY_TYPES: dict[str, str] = {
    ExperienceKind.SUCCESS: "lesson",
    ExperienceKind.FAILURE: "error",
    ExperienceKind.DECISION: "decision",
    ExperienceKind.PATTERN: "observation",
    ExperienceKind.LESSON: "lesson",
    ExperienceKind.SKILL_CANDIDATE: "skill",
}
