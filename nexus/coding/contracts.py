"""Coding-agent contracts (New Plan §15.1 / §15.2 / §15.6).

The phase thesis — NEXUS stops *understanding* code and starts
*changing* it. §15.1 fixes the Coding Agent Contract: one agent,
seven operations, one callable dispatcher::

    analyze   plan   edit   run   test   debug   review

§15.2 fixes the ten specialists (role names verbatim)::

    architect  frontend  backend  database  devops  debugger
    tester  security  performance  reviewer

§15.6 fixes the loop — eight stages, this exact order::

    Understand → Plan → Edit → Build → Test → Debug → Retest → Review

The three studied ecosystems stay MODE B/D (Plan §0.2/§0.4 — zero
imports, patterns only): OpenHands contributed the agent-abstraction /
event-loop / sandboxed-execution framing, OpenCode the session
persistence and client/server split, Cline the session trail (files
read, files edited, tool-call records). None of their code is
imported; the shapes below are NEXUS-native (Plan §61: *NEXUS owns
coding-agent semantics*).

عقود وكيل البرمجة — سبع عمليات وعشرة مختصين وحلقة من ثماني مراحل
بهذا الترتيب حرفيًا؛ NEXUS يملك الدلالات والمراجع خارج الاستيراد.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ------------------------------------------------------------- §15.1 kinds


class CodingError(Exception):
    """Coding-agent misuse or operation failure."""


class InvalidCodingContractError(CodingError):
    """A request/edit/verdict record violates the §15 contract."""


#: §15.1 — the seven operations, verbatim (values are snake_case per
#: codebase convention; the mapping to the plan's names is one-to-one).
CODING_OPERATION_KINDS: tuple[str, ...] = (
    "analyze",
    "plan",
    "edit",
    "run",
    "test",
    "debug",
    "review",
)


class CodingOperationKind(Enum):
    """The §15.1 operation vocabulary — exactly seven members."""

    ANALYZE = "analyze"
    PLAN = "plan"
    EDIT = "edit"
    RUN = "run"
    TEST = "test"
    DEBUG = "debug"
    REVIEW = "review"

    @classmethod
    def from_value(cls, value: str | CodingOperationKind) -> CodingOperationKind:
        """Coerce a plan name (any case) or member into the member."""
        if isinstance(value, cls):
            return value
        name = str(value).strip().lower()
        for member in cls:
            if member.value == name or member.name.lower() == name:
                return member
        raise InvalidCodingContractError(
            f"unknown coding operation {value!r} — expected one of {CODING_OPERATION_KINDS}"
        )


class OperationStatus(Enum):
    """Every §15.1 operation answers ok or fail — never silently."""

    OK = "ok"
    FAIL = "fail"

    @classmethod
    def from_value(cls, value: str | OperationStatus) -> OperationStatus:
        """Coerce a status name (any case) or member into the member."""
        if isinstance(value, cls):
            return value
        name = str(value).strip().lower()
        for member in cls:
            if member.value == name:
                return member
        raise InvalidCodingContractError(f"unknown operation status {value!r}")


# ------------------------------------------------------- §15.2 specialists

#: §15.2 — the ten specialist roles, verbatim.
SPECIALIST_ROLES: tuple[str, ...] = (
    "architect",
    "frontend",
    "backend",
    "database",
    "devops",
    "debugger",
    "tester",
    "security",
    "performance",
    "reviewer",
)


# -------------------------------------------------------- §15.6 the loop

#: §15.6 — the eight loop stages, verbatim and in plan order.
CODING_LOOP_STAGES: tuple[str, ...] = (
    "understand",
    "plan",
    "edit",
    "build",
    "test",
    "debug",
    "retest",
    "review",
)


class CodingLoopStage(Enum):
    """The §15.6 stage vocabulary — exactly eight members, plan order."""

    UNDERSTAND = "understand"
    PLAN = "plan"
    EDIT = "edit"
    BUILD = "build"
    TEST = "test"
    DEBUG = "debug"
    RETEST = "retest"
    REVIEW = "review"

    @classmethod
    def from_value(cls, value: str | CodingLoopStage) -> CodingLoopStage:
        """Coerce a stage name (any case) or member into the member."""
        if isinstance(value, cls):
            return value
        name = str(value).strip().lower()
        for member in cls:
            if member.value == name or member.name.lower() == name:
                return member
        raise InvalidCodingContractError(
            f"unknown coding-loop stage {value!r} — expected one of {CODING_LOOP_STAGES}"
        )


#: The loop order as members (harness-provable: list(LOOP_STAGE_ORDER)
#: == the §15.6 sequence).
LOOP_STAGE_ORDER: tuple[CodingLoopStage, ...] = (
    CodingLoopStage.UNDERSTAND,
    CodingLoopStage.PLAN,
    CodingLoopStage.EDIT,
    CodingLoopStage.BUILD,
    CodingLoopStage.TEST,
    CodingLoopStage.DEBUG,
    CodingLoopStage.RETEST,
    CodingLoopStage.REVIEW,
)


# ------------------------------------------------------- §15.1 edit shape


@dataclass(slots=True)
class EditAction:
    """One §15.1 edit — a path plus exactly one change mode.

    ``path``        — workspace-relative, forward slashes.
    ``old``/``new`` — replace mode: the first (or every) occurrence of
                      ``old`` is replaced by ``new``.
    ``content``     — rewrite mode: the whole file becomes this text.
    ``description`` — why (the plan step's rationale, echoed).

    Replace mode replaces **every** occurrence (the honest whole-file
    fix; a count of zero is a failure, never a silent no-op).
    """

    path: str
    old: str = ""
    new: str = ""
    content: str | None = None
    description: str = ""
    replace_all: bool = True

    def __post_init__(self) -> None:
        self.path = str(self.path).strip().replace("\\", "/")
        if not self.path:
            raise InvalidCodingContractError("edit action needs a non-empty path")
        rewrite = self.content is not None
        replace = bool(self.old) or bool(self.new)
        if rewrite and replace:
            raise InvalidCodingContractError(
                f"edit {self.path!r}: choose replace (old/new) or rewrite (content), not both"
            )
        if not rewrite and (not self.old or not self.new):
            raise InvalidCodingContractError(
                f"edit {self.path!r}: replace mode needs both old and new"
            )

    @property
    def mode(self) -> str:
        return "rewrite" if self.content is not None else "replace"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "old": self.old,
            "new": self.new,
            "content": self.content,
            "description": self.description,
            "replace_all": self.replace_all,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EditAction:
        return cls(
            path=str(data["path"]),
            old=str(data.get("old") or ""),
            new=str(data.get("new") or ""),
            content=data.get("content"),
            description=str(data.get("description") or ""),
            replace_all=bool(data.get("replace_all", True)),
        )


@dataclass(slots=True)
class PlanStep:
    """One §15.1 plan step — what to change, where, and how.

    ``step_id``      — ordinal id (``s1``, ``s2``…) inside one plan.
    ``description``  — the change in one sentence.
    ``target_files`` — workspace-relative paths the step touches.
    ``actions``      — concrete :class:`EditAction` sequence (may be
                       empty for investigation-only steps).
    ``rationale``    — why this step serves the goal.
    """

    step_id: str
    description: str
    target_files: tuple[str, ...] = ()
    actions: tuple[EditAction, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        self.target_files = tuple(self.target_files)
        self.actions = tuple(self.actions)
        if not self.step_id or not self.description.strip():
            raise InvalidCodingContractError("plan step needs id and description")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "target_files": list(self.target_files),
            "actions": [action.to_dict() for action in self.actions],
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlanStep:
        return cls(
            step_id=str(data["step_id"]),
            description=str(data["description"]),
            target_files=tuple(data.get("target_files") or ()),
            actions=tuple(EditAction.from_dict(a) for a in data.get("actions") or ()),
            rationale=str(data.get("rationale") or ""),
        )


@dataclass(slots=True)
class DebugFinding:
    """One §15.1 debug finding — a failing test plus a hypothesis.

    ``test``          — the failing test node id (``file::test``).
    ``hypothesis``    — the best current explanation.
    ``evidence``      — stderr/output excerpts supporting it.
    ``suggested_fix`` — an :class:`EditAction` when a recipe exists
                        (else ``None`` — hypotheses only, honestly).
    ``lessons``       — §13 lesson texts consulted for this finding.
    """

    test: str
    hypothesis: str
    evidence: tuple[str, ...] = ()
    suggested_fix: EditAction | None = None
    lessons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.evidence = tuple(self.evidence)
        self.lessons = tuple(self.lessons)
        if not self.test.strip() or not self.hypothesis.strip():
            raise InvalidCodingContractError("debug finding needs test and hypothesis")

    def to_dict(self) -> dict[str, Any]:
        return {
            "test": self.test,
            "hypothesis": self.hypothesis,
            "evidence": list(self.evidence),
            "suggested_fix": self.suggested_fix.to_dict() if self.suggested_fix else None,
            "lessons": list(self.lessons),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DebugFinding:
        fix = data.get("suggested_fix")
        return cls(
            test=str(data["test"]),
            hypothesis=str(data["hypothesis"]),
            evidence=tuple(data.get("evidence") or ()),
            suggested_fix=EditAction.from_dict(fix) if fix else None,
            lessons=tuple(data.get("lessons") or ()),
        )


# ------------------------------------------------------------ §15.1 review


@dataclass(slots=True)
class ReviewCheck:
    """One review checklist rule and its outcome."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReviewCheck:
        return cls(
            name=str(data["name"]),
            passed=bool(data["passed"]),
            detail=str(data.get("detail") or ""),
        )


@dataclass(slots=True)
class ReviewVerdict:
    """The §15.1 review verdict — approved or rejected, with reasons.

    ``approved`` — all checklist rules passed.
    ``reasons``  — human-readable lines (always non-empty).
    ``checks``   — the deterministic checklist that decided it.
    """

    approved: bool
    reasons: tuple[str, ...] = ()
    checks: tuple[ReviewCheck, ...] = ()

    def __post_init__(self) -> None:
        self.reasons = tuple(self.reasons)
        self.checks = tuple(self.checks)
        if not self.reasons:
            raise InvalidCodingContractError("review verdict needs at least one reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "reasons": list(self.reasons),
            "checks": [check.to_dict() for check in self.checks],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReviewVerdict:
        return cls(
            approved=bool(data["approved"]),
            reasons=tuple(data.get("reasons") or ()),
            checks=tuple(ReviewCheck.from_dict(c) for c in data.get("checks") or ()),
        )


# ------------------------------------------------- §15.1/§15.5 session trail


@dataclass(slots=True)
class ToolCallRecord:
    """One tool call observed during a coding session (Cline's trail)."""

    name: str
    detail: str = ""
    ok: bool = True
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ToolCallRecord:
        return cls(
            name=str(data["name"]),
            detail=str(data.get("detail") or ""),
            ok=bool(data.get("ok", True)),
            duration_ms=float(data.get("duration_ms", 0.0)),
        )


@dataclass(slots=True)
class CodingSessionRecord:
    """The §15.5-inspired session trail (Cline MODE D — zero imports).

    ``files_read``   — every file the agent read, first-seen order.
    ``files_edited`` — every file the agent changed, first-seen order.
    ``tool_calls``   — the full tool-call trail (run/test/debug…).
    ``commits``      — commit ids linked through the nexus git module
                       when its API allows it (loose coupling: the
                       phase-15 git seat is still a placeholder, so
                       the trail records what exists, never fakes it).
    """

    session_id: str
    goal: str = ""
    started_at: str = ""
    updated_at: str = ""
    status: str = "open"
    files_read: tuple[str, ...] = ()
    files_edited: tuple[str, ...] = ()
    tool_calls: tuple[ToolCallRecord, ...] = ()
    commits: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.files_read = tuple(self.files_read)
        self.files_edited = tuple(self.files_edited)
        self.tool_calls = tuple(self.tool_calls)
        self.commits = tuple(self.commits)
        if not self.session_id.strip():
            raise InvalidCodingContractError("coding session needs an id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "files_read": list(self.files_read),
            "files_edited": list(self.files_edited),
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "commits": list(self.commits),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CodingSessionRecord:
        return cls(
            session_id=str(data["session_id"]),
            goal=str(data.get("goal") or ""),
            started_at=str(data.get("started_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            status=str(data.get("status") or "open"),
            files_read=tuple(data.get("files_read") or ()),
            files_edited=tuple(data.get("files_edited") or ()),
            tool_calls=tuple(
                ToolCallRecord.from_dict(c) for c in data.get("tool_calls") or ()
            ),
            commits=tuple(data.get("commits") or ()),
        )


# --------------------------------------------------- §15.1 request/result


@dataclass(slots=True)
class OperationRequest:
    """One §15.1 request — kind + goal + payload.

    ``payload`` keys (all optional, documented per operation):
    analyze — ``db_path``, ``token_budget``;
    plan    — ``analyze`` (an analyze payload), ``targets``, ``fixes``;
    edit    — ``actions`` (EditAction dicts);
    run     — ``command`` (argv list) or ``script`` (one shell-free
              token string is rejected — argv only, no shell);
    test    — ``target`` (path, default the workspace root);
    debug   — ``failing_tests``, ``stderr``, ``fixes``, ``goal``;
    review  — ``test_outcome``, ``edits_applied``, ``debug_cycles``,
              ``max_debug_cycles``.
    """

    kind: CodingOperationKind
    goal: str
    workspace_root: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 120.0

    def __post_init__(self) -> None:
        self.kind = CodingOperationKind.from_value(self.kind)
        self.payload = dict(self.payload)
        if not self.goal.strip():
            raise InvalidCodingContractError("operation request needs a goal")
        if self.timeout_s <= 0:
            raise InvalidCodingContractError("timeout_s must be > 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "goal": self.goal,
            "workspace_root": self.workspace_root,
            "payload": dict(self.payload),
            "timeout_s": self.timeout_s,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OperationRequest:
        return cls(
            kind=CodingOperationKind.from_value(data["kind"]),
            goal=str(data["goal"]),
            workspace_root=str(data.get("workspace_root") or ""),
            payload=dict(data.get("payload") or {}),
            timeout_s=float(data.get("timeout_s", 120.0)),
        )


@dataclass(slots=True)
class OperationResult:
    """One §15.1 result — kind, status, duration, payload, summary.

    Every operation measures ``duration_ms``, answers ``ok``/``fail``,
    and leaves its evidence in ``payload`` (kind-specific serialized
    outcome dataclasses — see :mod:`nexus.coding.operations`).
    """

    kind: CodingOperationKind
    status: OperationStatus
    duration_ms: float
    summary: str
    error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = CodingOperationKind.from_value(self.kind)
        self.status = self.status if isinstance(self.status, OperationStatus) else (
            OperationStatus.from_value(self.status)
        )
        self.payload = dict(self.payload)

    @property
    def ok(self) -> bool:
        return self.status is OperationStatus.OK

    @classmethod
    def ok_result(
        cls,
        kind: CodingOperationKind,
        duration_ms: float,
        summary: str,
        payload: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        return cls(
            kind=kind,
            status=OperationStatus.OK,
            duration_ms=round(float(duration_ms), 3),
            summary=summary,
            payload=dict(payload or {}),
        )

    @classmethod
    def fail_result(
        cls,
        kind: CodingOperationKind,
        duration_ms: float,
        summary: str,
        error: str,
        payload: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        return cls(
            kind=kind,
            status=OperationStatus.FAIL,
            duration_ms=round(float(duration_ms), 3),
            summary=summary,
            error=error,
            payload=dict(payload or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "error": self.error,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OperationResult:
        return cls(
            kind=CodingOperationKind.from_value(data["kind"]),
            status=OperationStatus.from_value(data["status"]),
            duration_ms=float(data.get("duration_ms", 0.0)),
            summary=str(data.get("summary") or ""),
            error=str(data.get("error") or ""),
            payload=dict(data.get("payload") or {}),
        )


# ------------------------------------------- kind-specific outcome shapes


@dataclass(slots=True)
class AnalyzeSummary:
    """analyze payload — the §14-indexed project, summarized.

    ``top_files`` — (path, score) pairs from the §14.8 repository map.
    ``map_text``  — the rendered map (token-budgeted, hub-first).
    """

    root: str
    files_indexed: int = 0
    files_parsed: int = 0
    symbols: int = 0
    test_files: tuple[str, ...] = ()
    entry_points: tuple[str, ...] = ()
    top_files: tuple[tuple[str, float], ...] = ()
    languages: tuple[str, ...] = ()
    map_text: str = ""

    def __post_init__(self) -> None:
        self.test_files = tuple(self.test_files)
        self.entry_points = tuple(self.entry_points)
        self.top_files = tuple((str(p), float(s)) for p, s in self.top_files)
        self.languages = tuple(self.languages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "files_indexed": self.files_indexed,
            "files_parsed": self.files_parsed,
            "symbols": self.symbols,
            "test_files": list(self.test_files),
            "entry_points": list(self.entry_points),
            "top_files": [[path, score] for path, score in self.top_files],
            "languages": list(self.languages),
            "map_text": self.map_text,
        }


@dataclass(slots=True)
class PlanOutcome:
    """plan payload — ordered steps toward the goal."""

    steps: tuple[PlanStep, ...] = ()
    target_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.steps = tuple(self.steps)
        self.target_files = tuple(self.target_files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "target_files": list(self.target_files),
        }


@dataclass(slots=True)
class FileDiff:
    """edit payload — before/after evidence for one file."""

    path: str
    before_sha: str = ""
    after_sha: str = ""
    before_lines: int = 0
    after_lines: int = 0
    occurrences: int = 0
    applied: bool = False
    error: str = ""
    #: stale bytecode caches purged for this file (see the CI's catch).
    bytecode_purged: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "before_sha": self.before_sha,
            "after_sha": self.after_sha,
            "before_lines": self.before_lines,
            "after_lines": self.after_lines,
            "occurrences": self.occurrences,
            "applied": self.applied,
            "error": self.error,
            "bytecode_purged": list(self.bytecode_purged),
        }


@dataclass(slots=True)
class EditOutcome:
    """edit payload — applied/failed counts + per-file diffs."""

    applied: int = 0
    failed: int = 0
    diffs: tuple[FileDiff, ...] = ()
    git_staging: str = "recorded"  # staged | recorded | unavailable

    def __post_init__(self) -> None:
        self.diffs = tuple(self.diffs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "failed": self.failed,
            "diffs": [diff.to_dict() for diff in self.diffs],
            "git_staging": self.git_staging,
            "bytecode_purged": sum(len(diff.bytecode_purged) for diff in self.diffs),
        }


@dataclass(slots=True)
class RunOutcome:
    """run payload — one command, captured honestly."""

    command: tuple[str, ...] = ()
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    def __post_init__(self) -> None:
        self.command = tuple(self.command)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
        }


@dataclass(slots=True)
class TestOutcome:
    """test payload — the pytest-shaped evidence."""

    command: tuple[str, ...] = ()
    target: str = ""
    runner: str = "pytest"  # harness | pytest
    exit_code: int = -1
    passed: int = 0
    failed: int = 0
    failing_tests: tuple[str, ...] = ()
    stdout_tail: str = ""
    stderr_tail: str = ""

    def __post_init__(self) -> None:
        self.command = tuple(self.command)
        self.failing_tests = tuple(self.failing_tests)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "target": self.target,
            "runner": self.runner,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "failed": self.failed,
            "failing_tests": list(self.failing_tests),
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


@dataclass(slots=True)
class DebugOutcome:
    """debug payload — findings + the lessons consulted."""

    findings: tuple[DebugFinding, ...] = ()
    lessons_consulted: int = 0
    fixes_available: int = 0

    def __post_init__(self) -> None:
        self.findings = tuple(self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [finding.to_dict() for finding in self.findings],
            "lessons_consulted": self.lessons_consulted,
            "fixes_available": self.fixes_available,
        }


@dataclass(slots=True)
class ReviewOutcome:
    """review payload — the verdict plus the evidence it rested on."""

    verdict: ReviewVerdict
    tests_passed: bool = False
    edits_applied: int = 0
    debug_cycles: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.to_dict(),
            "tests_passed": self.tests_passed,
            "edits_applied": self.edits_applied,
            "debug_cycles": self.debug_cycles,
        }


def parse_edit_actions(raw: Sequence[Mapping[str, Any] | EditAction]) -> tuple[EditAction, ...]:
    """Coerce a payload list into :class:`EditAction` tuples."""
    actions: list[EditAction] = []
    for item in raw:
        if isinstance(item, EditAction):
            actions.append(item)
        else:
            actions.append(EditAction.from_dict(item))
    return tuple(actions)
