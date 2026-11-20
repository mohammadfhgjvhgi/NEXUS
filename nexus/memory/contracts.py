"""Memory contracts (Final Build Plan §13.1 / New Plan §12.1–§12.3).

The five names are verbatim from the plan::

    MemoryProvider
    MemoryRecord
    MemoryQuery
    MemoryScope
    MemoryEvidence

§12.2 fixes the hierarchy — twelve scopes, verbatim::

    GLOBAL · USER · PROJECT · WORKSPACE · TASK · SESSION · AGENT
    KNOWLEDGE · DECISION · LESSON · SKILL · ERROR

§12.3 fixes the metadata — eleven fields, verbatim::

    id · type · scope · content · source · confidence
    created_at · updated_at · expires_at · project · workspace · task

§13.1 fixes the verb set the provider must expose::

    remember · retrieve · search · update · forget · summarize · link

Architecture invariant (Plan §61): *NEXUS owns Memory semantics* —
these contracts are NEXUS-native; every external engine (Qdrant §12.5,
Mem0 §12.6) enters behind them as an adapter and is replaceable.

عقود الذاكرة — الأسماء الخمسة والمستويات الاثنا عشر والحقول
الأحد عشر حرفيًا كما في الخطة؛ النواة تملك دلالات الذاكرة
والمحركات الخارجية تدخل خلف هذه العقود فقط.

Stdlib only.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# ----------------------------------------------------------------- errors


class MemoryError(Exception):
    """Memory misuse or backend failure."""


class InvalidMemoryError(MemoryError):
    """A record/query violates the §12.2/§12.3 contract."""


class MemoryNotFoundError(MemoryError):
    """The requested record id does not exist (or is forgotten)."""


# ------------------------------------------------------------ §12.2 scopes


class MemoryScope:
    """The twelve §12.2 scopes, verbatim vocabulary."""

    GLOBAL = "global"
    USER = "user"
    PROJECT = "project"
    WORKSPACE = "workspace"
    TASK = "task"
    SESSION = "session"
    AGENT = "agent"
    KNOWLEDGE = "knowledge"
    DECISION = "decision"
    LESSON = "lesson"
    SKILL = "skill"
    ERROR = "error"


MEMORY_SCOPES: tuple[str, ...] = (
    MemoryScope.GLOBAL,
    MemoryScope.USER,
    MemoryScope.PROJECT,
    MemoryScope.WORKSPACE,
    MemoryScope.TASK,
    MemoryScope.SESSION,
    MemoryScope.AGENT,
    MemoryScope.KNOWLEDGE,
    MemoryScope.DECISION,
    MemoryScope.LESSON,
    MemoryScope.SKILL,
    MemoryScope.ERROR,
)

#: The container ladder (§12.2 reading): each level narrows visibility.
#: The five semantic scopes (KNOWLEDGE…ERROR) are *libraries* that ride
#: the ladder via their container fields instead of owning a rung.
CONTAINER_SCOPES: tuple[str, ...] = (
    MemoryScope.GLOBAL,
    MemoryScope.USER,
    MemoryScope.PROJECT,
    MemoryScope.WORKSPACE,
    MemoryScope.TASK,
)


# ------------------------------------------------------------- §12.3 types

#: Canonical record types. §12.2 already dedicates scopes to the semantic
#: categories (KNOWLEDGE/DECISION/LESSON/SKILL/ERROR); ``type`` carries
#: the *kind of content* inside whichever scope the record lives in.
class MemoryType:
    OBSERVATION = "observation"
    FACT = "fact"
    PREFERENCE = "preference"
    RULE = "rule"
    DECISION = "decision"
    LESSON = "lesson"
    SKILL = "skill"
    ERROR = "error"
    KNOWLEDGE = "knowledge"
    SUMMARY = "summary"
    EVENT = "event"
    NOTE = "note"


MEMORY_TYPES: tuple[str, ...] = (
    MemoryType.OBSERVATION,
    MemoryType.FACT,
    MemoryType.PREFERENCE,
    MemoryType.RULE,
    MemoryType.DECISION,
    MemoryType.LESSON,
    MemoryType.SKILL,
    MemoryType.ERROR,
    MemoryType.KNOWLEDGE,
    MemoryType.SUMMARY,
    MemoryType.EVENT,
    MemoryType.NOTE,
)

#: Evidence capture methods (§12.1 MemoryEvidence provenance).
EVIDENCE_METHODS: tuple[str, ...] = (
    "tool_run",
    "observation",
    "user_statement",
    "document",
    "research",
    "test",
    "system",
)

#: Canonical relationship verbs (§13.1 ``link``).
RELATIONSHIPS: tuple[str, ...] = (
    "links",
    "derived_from",
    "supersedes",
    "compressed_from",
    "evidence_for",
    "conflicts_with",
)


# --------------------------------------------------------- §12.1 evidence


@dataclass(frozen=True, slots=True)
class MemoryEvidence:
    """One provenance artifact attached to a record (§12.1).

    ``method``  — how the evidence was captured (EVIDENCE_METHODS).
    ``uri``     — where it lives (path, URL, task id…).
    ``snippet`` — the excerpt that backs the record's content.
    """

    method: str
    uri: str = ""
    snippet: str = ""
    captured_at: str = ""

    def validate(self) -> None:
        if self.method not in EVIDENCE_METHODS:
            raise InvalidMemoryError(
                f"evidence.method must be one of {EVIDENCE_METHODS}, "
                f"got {self.method!r}"
            )
        if not self.uri and not self.snippet:
            raise InvalidMemoryError(
                "evidence needs a uri or a snippet — evidence with no "
                "provenance is not evidence"
            )


EVIDENCE_FIELDS: tuple[str, ...] = (
    "method",
    "uri",
    "snippet",
    "captured_at",
)


# ---------------------------------------------------------- §12.1 record


_ID_PATTERN = re.compile(r"^mem_[0-9a-f]{16}$")

MEMORY_RECORD_FIELDS: tuple[str, ...] = (
    # §12.3 verbatim (eleven)
    "id",
    "type",
    "scope",
    "content",
    "source",
    "confidence",
    "created_at",
    "updated_at",
    "expires_at",
    "project",
    "workspace",
    "task",
    # house seams (documented beyond §12.3)
    "session",
    "agent",
    "conflict_key",
    "evidence",
    "active",
    "forgotten_at",
    "forget_reason",
)


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds (house format)."""
    return datetime.now(UTC).isoformat()


def new_memory_id(seed: str = "") -> str:
    """Deterministic id for tests (seeded), random otherwise.

    Format ``mem_`` + 16 hex — short, greppable, collision-safe for the
    local single-writer store (the SQLite primary key is the final word).
    """
    import hashlib
    import secrets

    if seed:
        digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).hexdigest()
    else:
        digest = secrets.token_hex(8)
    return f"mem_{digest}"


@dataclass(slots=True)
class MemoryRecord:
    """One memory — the §12.3 eleven metadata fields verbatim, plus the
    house seams the plan implies (session/agent containers for the
    §12.2 ladder, conflict_key for §12.8, evidence for §12.1).

    ``source`` — who wrote it ("user", "agent:<id>", "system",
    "tool:<name>", "learning"). ``confidence`` — 0.0–1.0.
    """

    id: str
    type: str
    scope: str
    content: str
    source: str
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    expires_at: str | None = None
    project: str | None = None
    workspace: str | None = None
    task: str | None = None
    # house seams
    session: str | None = None
    agent: str | None = None
    conflict_key: str | None = None
    evidence: tuple[MemoryEvidence, ...] = ()
    active: bool = True
    forgotten_at: str | None = None
    forget_reason: str | None = None

    def __post_init__(self) -> None:
        if not _ID_PATTERN.match(self.id):
            raise InvalidMemoryError(
                "memory id must be 'mem_' + 16 hex (mem_abcd0123456789ef)"
            )
        if self.scope not in MEMORY_SCOPES:
            raise InvalidMemoryError(
                f"scope must be one of the twelve §12.2 scopes, got {self.scope!r}"
            )
        if self.type not in MEMORY_TYPES:
            raise InvalidMemoryError(
                f"type must be one of {MEMORY_TYPES}, got {self.type!r}"
            )
        if not self.content.strip():
            raise InvalidMemoryError("memory content must not be empty")
        if not self.source.strip():
            raise InvalidMemoryError("memory source must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidMemoryError(
                f"confidence must be within [0.0, 1.0], got {self.confidence}"
            )
        now = utc_now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at
        # container-scope coherence (§12.2): a TASK record names its task…
        if self.scope == MemoryScope.PROJECT and not self.project:
            raise InvalidMemoryError("a PROJECT memory must set project=")
        if self.scope == MemoryScope.WORKSPACE and not self.workspace:
            raise InvalidMemoryError("a WORKSPACE memory must set workspace=")
        if self.scope == MemoryScope.TASK and not self.task:
            raise InvalidMemoryError("a TASK memory must set task=")
        if self.scope == MemoryScope.SESSION and not self.session:
            raise InvalidMemoryError("a SESSION memory must set session=")
        if self.scope == MemoryScope.AGENT and not self.agent:
            raise InvalidMemoryError("an AGENT memory must set agent=")

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
            "type": self.type,
            "scope": self.scope,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "project": self.project,
            "workspace": self.workspace,
            "task": self.task,
            "session": self.session,
            "agent": self.agent,
            "conflict_key": self.conflict_key,
            "evidence": self.evidence_rows(),
            "active": self.active,
            "forgotten_at": self.forgotten_at,
            "forget_reason": self.forget_reason,
        }


# ------------------------------------------------------------ scope rules


def scope_visible(record: MemoryRecord, query: MemoryQuery) -> bool:
    """The §12.2 visibility ladder — one pure rule, tested to death.

    * GLOBAL and USER — visible to every query (single-operator system,
      Spec §2.3: one local user).
    * PROJECT/WORKSPACE/TASK/SESSION/AGENT — the query's matching
      container must equal the record's (strict isolation: task A never
      sees task B).
    * The semantic libraries (KNOWLEDGE/DECISION/LESSON/SKILL/ERROR) —
      visible whenever their container fields are unset (library-wide)
      or match the query's containers exactly.
    """
    scope = record.scope
    if scope in (MemoryScope.GLOBAL, MemoryScope.USER):
        return True
    if scope == MemoryScope.PROJECT:
        return bool(query.project) and record.project == query.project
    if scope == MemoryScope.WORKSPACE:
        return bool(query.workspace) and record.workspace == query.workspace
    if scope == MemoryScope.TASK:
        return bool(query.task) and record.task == query.task
    if scope == MemoryScope.SESSION:
        return bool(query.session) and record.session == query.session
    if scope == MemoryScope.AGENT:
        return bool(query.agent) and record.agent == query.agent
    # semantic libraries: unset containers → library-wide visibility
    checks = (
        ("project", query.project),
        ("workspace", query.workspace),
        ("task", query.task),
        ("session", query.session),
        ("agent", query.agent),
    )
    for attr, want in checks:
        have = getattr(record, attr)
        if have is not None and have != want:
            return False
    return True


# ----------------------------------------------------------- §12.1 query


MEMORY_QUERY_FIELDS: tuple[str, ...] = (
    "text",
    "scope",
    "project",
    "workspace",
    "task",
    "session",
    "agent",
    "types",
    "limit",
    "min_confidence",
    "since",
    "until",
    "include_semantic",
    "vector_top_k",
)


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    """What the retrieval pipeline asks for (§12.1 / §12.7 head).

    ``text``             — the prompt/needle (lexical + semantic match).
    ``scope``            — optional scope filter (exact scope name).
    ``project``…``agent``— container context; also drives visibility.
    ``types``            — restrict to these record types.
    ``limit``            — max records returned.
    ``min_confidence``   — floor on record confidence.
    ``since``/``until``  — ISO bounds on updated_at.
    ``include_semantic`` — whether the vector stage runs at all.
    ``vector_top_k``     — candidate count from the vector stage.
    """

    text: str = ""
    scope: str | None = None
    project: str | None = None
    workspace: str | None = None
    task: str | None = None
    session: str | None = None
    agent: str | None = None
    types: tuple[str, ...] = ()
    limit: int = 20
    min_confidence: float = 0.0
    since: str | None = None
    until: str | None = None
    include_semantic: bool = True
    vector_top_k: int = 32

    def __post_init__(self) -> None:
        if self.scope is not None and self.scope not in MEMORY_SCOPES:
            raise InvalidMemoryError(
                f"query scope must be one of the twelve §12.2 scopes or None, "
                f"got {self.scope!r}"
            )
        bad_types = [t for t in self.types if t not in MEMORY_TYPES]
        if bad_types:
            raise InvalidMemoryError(
                f"query types must come from {MEMORY_TYPES}, got {bad_types}"
            )
        if self.limit < 1:
            raise InvalidMemoryError("query limit must be >= 1")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise InvalidMemoryError(
                f"min_confidence must be within [0.0, 1.0], got {self.min_confidence}"
            )
        if self.vector_top_k < 1:
            raise InvalidMemoryError("vector_top_k must be >= 1")


# --------------------------------------------------------- §13.1 provider


@dataclass(slots=True)
class MemorySearchHit:
    """One ranked search result — record plus how it was found.

    Mutable by design: the §12.7 pipeline *merges* stage scores onto
    the same hit (vector + lexical), then writes the final rank.
    """

    record: MemoryRecord
    score: float
    semantic: float = 0.0
    lexical: float = 0.0
    provenance: tuple[str, ...] = ()


@dataclass(slots=True)
class ForgetResult:
    """§12.9 outcome — what was forgotten, and where the audit lives."""

    forgotten: tuple[str, ...]
    action: str
    reason: str
    audit_rows: int


class MemoryProvider(ABC):
    """§13.1 abstraction — the seven verbs, verbatim:

    remember · retrieve · search · update · forget · summarize · link

    Implementations: :class:`~nexus.memory.engine.MemoryEngine` (the
    NEXUS-native default) and
    :class:`~nexus.memory.mem0_adapter.Mem0MemoryProvider` (§12.6
    adapter). The contract is the seam — swapping engines later means
    writing one more adapter, nothing else (Spec §61 invariant).
    """

    @abstractmethod
    def remember(
        self,
        content: str,
        *,
        type: str = MemoryType.FACT,  # noqa: A002 — verbatim §13.1 verb name
        scope: str = MemoryScope.GLOBAL,
        source: str = "system",
        confidence: float = 1.0,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
        conflict_key: str | None = None,
        expires_at: str | None = None,
        evidence: tuple[MemoryEvidence, ...] = (),
    ) -> MemoryRecord: ...

    @abstractmethod
    def search(self, query: MemoryQuery) -> list[MemorySearchHit]: ...

    @abstractmethod
    def retrieve(
        self,
        prompt: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
        limit: int = 16,
        budget_chars: int = 6000,
    ) -> Any: ...

    @abstractmethod
    def update(
        self,
        record_id: str,
        *,
        content: str | None = None,
        confidence: float | None = None,
        expires_at: str | None = None,
    ) -> MemoryRecord: ...

    @abstractmethod
    def forget(
        self,
        *,
        record_id: str | None = None,
        type: str | None = None,  # noqa: A002 — §12.9 category forget
        scope: str | None = None,  # noqa: A002 — §12.9 scope forget
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        reason: str = "operator request",
        requested_by: str = "operator",
        allow_global: bool = False,
    ) -> ForgetResult: ...

    @abstractmethod
    def summarize(
        self,
        *,
        record_ids: tuple[str, ...] = (),
        turns: tuple[dict[str, Any], ...] = (),
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
    ) -> MemoryRecord: ...

    @abstractmethod
    def link(
        self,
        record_id: str,
        related_id: str,
        relation: str = "links",
    ) -> None: ...
