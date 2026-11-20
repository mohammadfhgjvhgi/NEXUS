"""Coding agent operations (New Plan §15.1) — the seven verbs.

One contract: :class:`CodingAgent.execute(request) → result`. The
seven operations build strictly on what NEXUS already owns::

    analyze — the §14 index + repository map (never whole files)
    plan    — analyze result + goal → ordered steps and EditActions
    edit    — EditActions to disk: before-snapshot, atomic write,
              diff trail, git-module staging when its API exists
    run     — one argv command, timeout, captured stdout/stderr/exit
    test    — the harness's real runner when importable without side
              effects, else ``python -m pytest`` on the target
    debug   — failing tests + stderr + §13 lesson recall → findings
    review  — re-run tests + diff trail + deterministic checklist →
              verdict (approved/rejected with reasons)

Every operation measures ``duration_ms``, answers ok/fail, and
leaves its evidence in a kind-specific payload. Nothing here imports
an external coding agent (OpenHands/OpenCode/Cline stayed MODE B/D —
zero imports, ``vendor-staging/phase-15`` holds the study).

عمليات وكيل البرمجة السبع — عقد واحد، وتُبنى كل عملية على مراحل
NEXUS السابقة، وكل نتيجة تحمل إثباتها.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nexus.codeintel.contracts import detect_language
from nexus.codeintel.engine import build_codeintel_engine

from .contracts import (
    AnalyzeSummary,
    CodingError,
    CodingOperationKind,
    DebugFinding,
    DebugOutcome,
    EditAction,
    EditOutcome,
    FileDiff,
    OperationRequest,
    OperationResult,
    OperationStatus,
    PlanOutcome,
    PlanStep,
    ReviewCheck,
    ReviewOutcome,
    ReviewVerdict,
    RunOutcome,
    TestOutcome,
    ToolCallRecord,
    parse_edit_actions,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from nexus.events import EventBus
    from nexus.learning.store import SQLiteLearningStore

    from .session import CodingSession

#: How much captured subprocess output is kept per stream (bytes-ish
#: in characters — the honest tail, not the whole firehose).
_OUTPUT_TAIL = 4000

#: Default token budget for the §14.8 map inside ``analyze``.
_DEFAULT_MAP_BUDGET = 512

#: Test-file conventions honored when collecting test files (the
#: §14.6 link conventions: ``test_*.py`` / ``*_test.py``).
_TEST_FILE_RE = re.compile(r"(^|/)test_[^/]+\.py$|(^|/)[^/]+_test\.py$")

#: pytest summary counters — the ``-q`` summary prints counts in either
#: order (``1 failed, 1 passed in 0.02s`` or ``2 passed in 0.01s``).
_SUMMARY_PASSED_RE = re.compile(r"(\d+)\s+passed\b")
_SUMMARY_FAILED_RE = re.compile(r"(\d+)\s+failed\b")

#: pytest short-summary failing line: ``FAILED nid - detail``.
_FAILED_LINE_RE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)(?:\s+-\s+(.*))?$")

#: The harness attribute we accept as the §7 real test-running path
#: (import-checked, never faked).
_HARNESS_RUNNER_ATTRS = ("run_tests", "code_run_tests")


def _tail(text: str, limit: int = _OUTPUT_TAIL) -> str:
    """Last ``limit`` characters of captured output."""
    return text if len(text) <= limit else text[-limit:]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _resolve_under_root(root: Path, relative: str) -> Path:
    """Resolve a workspace-relative path, refusing escapes."""
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and not candidate.is_relative_to(root_resolved):
        raise CodingError(f"path escapes the workspace: {relative!r}")
    return candidate


def _atomic_write(path: Path, content: str) -> None:
    """House-style write: temp file in the same dir + ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _invalidate_bytecode(source: Path) -> tuple[str, ...]:
    """Purge stale bytecode caches for an edited source file.

    CPython validates a ``.pyc`` against the source's mtime (as int
    seconds) and size. An edit that preserves size and lands within
    the same second — exactly a ``* → /`` fix on a fast machine — leaves
    the stale cache "valid", and the interpreter serves the OLD code to
    the very tests meant to verify the fix (the CI's catch, 2026-09-09:
    six loop tests failed only on the fast runner). A developer agent
    that edits must guarantee the next import sees the new source:
    purge the caches. Best effort — a cache that won't die must never
    kill the edit itself.
    """
    purged: list[str] = []
    cache_dir = source.parent / "__pycache__"
    if cache_dir.is_dir():
        for entry in sorted(cache_dir.glob(f"{source.stem}.cpython-*.pyc")):
            try:
                entry.unlink()
            except OSError:
                continue
            purged.append(str(entry))
    legacy = source.parent / f"{source.stem}.pyc"
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
        else:
            purged.append(str(legacy))
    return tuple(purged)


def _find_harness_runner() -> tuple[str, Any] | None:
    """The §7 harness's real test runner — only if importable, side-effect-free.

    The phase-6 harness ships the §41 contract but no direct
    ``run_tests``/``code_run_tests`` callable; the moment it grows one
    (or ``nexus.tests`` materializes it), the test operation routes
    through it. Until then we say so and fall back to ``python -m
    pytest``.
    """
    try:
        spec = importlib.util.find_spec("nexus.harness")
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    try:
        module = importlib.import_module("nexus.harness")
    except Exception:  # noqa: BLE001 — availability probe, never a crash
        return None
    for attr in _HARNESS_RUNNER_ATTRS:
        candidate = getattr(module, attr, None)
        if callable(candidate):
            return f"nexus.harness.{attr}", candidate
    return None


def _harness_run(runner: Any, target: str) -> TestOutcome | None:
    """Try the harness runner — one positional target, mapping back.

    Any surprise (signature, return shape) returns ``None`` and the
    caller falls back to pytest honestly — the harness path must
    never be faked or crash the operation.
    """
    try:
        answer = runner(target)
    except Exception:  # noqa: BLE001 — probe discipline
        return None
    if not isinstance(answer, Mapping):
        return None
    return TestOutcome(
        target=target,
        runner="harness",
        exit_code=int(answer.get("exit_code", -1)),
        passed=int(answer.get("passed", 0)),
        failed=int(answer.get("failed", 0)),
        failing_tests=tuple(str(t) for t in answer.get("failing_tests") or ()),
        stdout_tail=str(answer.get("stdout", ""))[:_OUTPUT_TAIL],
        stderr_tail=str(answer.get("stderr", ""))[:_OUTPUT_TAIL],
    )


def _parse_pytest_output(stdout: str, exit_code: int) -> tuple[int, int, tuple[str, ...]]:
    """(passed, failed, failing node ids) from a ``-q`` pytest run."""
    failing: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(("FAILED ", "ERROR ")):
            match = _FAILED_LINE_RE.match(line)
            if match:
                failing.append(match.group(1))
    m_passed = _SUMMARY_PASSED_RE.search(stdout)
    m_failed = _SUMMARY_FAILED_RE.search(stdout)
    passed = int(m_passed.group(1)) if m_passed else 0
    failed = int(m_failed.group(1)) if m_failed else 0
    if m_passed is None and m_failed is None:
        failed = len(failing) or (1 if exit_code != 0 else 0)
    failed = max(failed, len(failing))
    return passed, failed, tuple(failing)


def _source_file_for_test(node_id: str) -> str:
    """``tests/test_main.py::test_x`` → a likely source-file candidate.

    The §14.6 conventions mirrored: ``test_<module>.py`` tests
    ``<module>.py``; the last path segment wins.
    """
    path_part = node_id.split("::", 1)[0]
    name = Path(path_part).name
    if name.startswith("test_"):
        return name.removeprefix("test_")
    if name.endswith("_test.py"):
        return name.removesuffix("_test.py") + ".py"
    return name


class CodingAgent:
    """The §15.1 Coding Agent — one dispatcher, seven operations.

    ``workspace_root`` — where every path resolves (escapes refused).
    ``bus``            — optional canonical Event Bus (task/tool events).
    ``learning_store`` — optional §13 store consulted by ``debug``.
    ``session``        — optional :class:`~nexus.coding.session.CodingSession`
                         recording the Cline-style trail.
    ``index_db``       — optional §14 index location (default: the
                         engine's ``<root>/.nexus/codeintel.db``).
    """

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        bus: EventBus | None = None,
        learning_store: SQLiteLearningStore | None = None,
        session: CodingSession | None = None,
        index_db: str | Path | None = None,
    ) -> None:
        self._root = Path(workspace_root)
        self._bus = bus
        self._learning_store = learning_store
        self._session = session
        self._index_db = index_db

    # ---------------------------------------------------------- contract

    @property
    def workspace_root(self) -> Path:
        return self._root

    @property
    def bus(self) -> EventBus | None:
        """The canonical event bus this agent publishes through (if any)."""
        return self._bus

    @property
    def session(self) -> CodingSession | None:
        """The session trail this agent records into (if any)."""
        return self._session

    def execute(self, request: OperationRequest) -> OperationResult:
        """The §15.1 contract — one callable, all seven operations."""
        if request.workspace_root:
            root = Path(request.workspace_root)
            if root != self._root and root.resolve() != self._root.resolve():
                raise CodingError(
                    f"request workspace {request.workspace_root!r} is not this "
                    f"agent's workspace {str(self._root)!r}"
                )
        dispatch = {
            CodingOperationKind.ANALYZE: self.analyze,
            CodingOperationKind.PLAN: self.plan,
            CodingOperationKind.EDIT: self.edit,
            CodingOperationKind.RUN: self.run,
            CodingOperationKind.TEST: self.test,
            CodingOperationKind.DEBUG: self.debug,
            CodingOperationKind.REVIEW: self.review,
        }
        handler = dispatch.get(request.kind)
        if handler is None:  # pragma: no cover — kind enum is closed
            raise CodingError(f"unhandled operation kind: {request.kind!r}")
        started = time.perf_counter()
        try:
            result = handler(request)
        except Exception as exc:  # noqa: BLE001 — one honest failure record
            result = OperationResult.fail_result(
                request.kind,
                (time.perf_counter() - started) * 1000.0,
                f"{request.kind.value} crashed",
                f"{type(exc).__name__}: {exc}",
            )
        self._note_tool_call(request, result)
        return result

    # -------------------------------------------------------- §15.1 analyze

    def analyze(self, request: OperationRequest) -> OperationResult:
        """analyze — index the workspace, answer the project summary."""
        started = time.perf_counter()
        budget = int(request.payload.get("token_budget", _DEFAULT_MAP_BUDGET))
        engine = build_codeintel_engine(
            self._root, db_path=self._index_db, prefer="auto"
        )
        try:
            stats = engine.scan()
            links = engine.test_links()
            test_files = sorted({link.test_file for link in links})
            for entry in engine.repo_map(token_budget=budget).entries:
                if _TEST_FILE_RE.search(entry.file):
                    test_files.append(entry.file)
            test_files = sorted(set(test_files))
            map_result = engine.repo_map(token_budget=budget)
            top_files = tuple(
                (entry.file, round(entry.score, 4)) for entry in map_result.entries
            )
            languages = tuple(
                sorted(
                    {
                        lang
                        for lang in (detect_language(path) for path, _ in top_files)
                        if lang
                    }
                )
            )
            summary = AnalyzeSummary(
                root=str(self._root),
                files_indexed=stats.files_indexed,
                files_parsed=stats.files_parsed,
                symbols=stats.symbols,
                test_files=tuple(f for f in test_files if not f.startswith(".nexus/")),
                entry_points=tuple(engine.entry_points()),
                top_files=tuple(
                    (path, score) for path, score in top_files if not path.startswith(".nexus/")
                ),
                languages=languages,
                map_text=map_result.render(),
            )
        finally:
            engine.close()
        payload = summary.to_dict()
        payload["engine"] = "codeintel"  # the §14 façade answered
        return OperationResult.ok_result(
            CodingOperationKind.ANALYZE,
            (time.perf_counter() - started) * 1000.0,
            (
                f"{summary.files_indexed} files indexed, {summary.symbols} symbols, "
                f"{len(summary.test_files)} test files"
            ),
            payload,
        )

    # ---------------------------------------------------------- §15.1 plan

    def plan(self, request: OperationRequest) -> OperationResult:
        """plan — analyze evidence + goal → ordered steps and edits.

        The fix recipes come with the goal (``payload['fixes']`` —
        EditAction dicts): in the full system the model proposes them;
        in this stdlib-only phase the caller's declared recipe is the
        proposal. Without recipes the plan is honest investigation
        steps — no fabricated edits.
        """
        started = time.perf_counter()
        payload = request.payload
        analyze = dict(payload.get("analyze") or {})
        fixes = parse_edit_actions(payload.get("fixes") or ())
        targets = [str(t) for t in payload.get("targets") or ()]

        by_file: dict[str, list[EditAction]] = {}
        for fix in fixes:
            by_file.setdefault(fix.path, []).append(fix)
        if not targets:
            targets = list(by_file)
        if not targets:
            top = analyze.get("top_files") or []
            targets = [
                str(path)
                for path, _score in top[:3]
                if not _TEST_FILE_RE.search(str(path)) and not str(path).startswith(".nexus/")
            ]
        if not targets:
            targets = sorted(analyze.get("test_files") or [])[:1]

        steps: list[PlanStep] = []
        for ordinal, path in enumerate(sorted(dict.fromkeys(targets)), start=1):
            actions = tuple(by_file.get(path, ()))
            if actions:
                description = (
                    f"Apply the fix for the goal in {path} "
                    f"({sum(1 for a in actions)} edit action(s))"
                )
                rationale = "declared fix recipe for the goal"
            else:
                description = f"Investigate and prepare the change for the goal in {path}"
                rationale = "target selected from the analyze evidence"
            steps.append(
                PlanStep(
                    step_id=f"s{ordinal}",
                    description=description,
                    target_files=(path,),
                    actions=actions,
                    rationale=rationale,
                )
            )
        if not steps:
            steps.append(
                PlanStep(
                    step_id="s1",
                    description=(
                        "No code target identified — read the analyze summary "
                        "and narrow the goal before editing"
                    ),
                    rationale="honest empty plan: no target files, no fabricated edits",
                )
            )
        outcome = PlanOutcome(steps=tuple(steps), target_files=tuple(targets))
        return OperationResult.ok_result(
            CodingOperationKind.PLAN,
            (time.perf_counter() - started) * 1000.0,
            f"{len(outcome.steps)} step(s), targets: {', '.join(outcome.target_files) or '(none)'}",
            outcome.to_dict(),
        )

    # ---------------------------------------------------------- §15.1 edit

    def edit(self, request: OperationRequest) -> OperationResult:
        """edit — apply EditActions with before-snapshots and a diff trail."""
        started = time.perf_counter()
        actions = parse_edit_actions(request.payload.get("actions") or ())
        if not actions:
            return OperationResult.fail_result(
                CodingOperationKind.EDIT,
                (time.perf_counter() - started) * 1000.0,
                "no edit actions supplied",
                "payload['actions'] is empty",
            )
        diffs: list[FileDiff] = []
        applied = failed = 0
        for action in actions:
            diffs.append(self._apply_action(action))
        for diff in diffs:
            if diff.applied:
                applied += 1
            else:
                failed += 1
        outcome = EditOutcome(
            applied=applied,
            failed=failed,
            diffs=tuple(diffs),
            git_staging=self._git_stage_note(
                [diff.path for diff in diffs if diff.applied]
            ),
        )
        status = OperationStatus.OK if failed == 0 else OperationStatus.FAIL
        summary = f"{applied} edit(s) applied, {failed} failed"
        error = "" if failed == 0 else "; ".join(
            f"{diff.path}: {diff.error}" for diff in diffs if not diff.applied
        )
        return OperationResult(
            kind=CodingOperationKind.EDIT,
            status=status,
            duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
            summary=summary,
            error=error,
            payload=outcome.to_dict(),
        )

    def _apply_action(self, action: EditAction) -> FileDiff:
        """One action → one diff record (never a silent no-op)."""
        try:
            target = _resolve_under_root(self._root, action.path)
        except CodingError as exc:
            return FileDiff(path=action.path, applied=False, error=str(exc))
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        self._note_read(action.path)
        before_lines = before.count("\n") + (1 if before and not before.endswith("\n") else 0)
        try:
            if action.content is not None:
                after = action.content
            else:
                occurrences = before.count(action.old)
                if occurrences == 0:
                    return FileDiff(
                        path=action.path,
                        before_sha=_sha256(before),
                        before_lines=before_lines,
                        applied=False,
                        error=f"pattern not found: {action.old[:60]!r}",
                    )
                if action.replace_all:
                    after = before.replace(action.old, action.new)
                else:
                    after = before.replace(action.old, action.new, 1)
            _atomic_write(target, after)
        except OSError as exc:
            return FileDiff(
                path=action.path,
                before_sha=_sha256(before),
                before_lines=before_lines,
                applied=False,
                error=f"write failed: {exc}",
            )
        purged = _invalidate_bytecode(target)
        after_lines = after.count("\n") + (1 if after and not after.endswith("\n") else 0)
        diff = FileDiff(
            path=action.path,
            before_sha=_sha256(before),
            after_sha=_sha256(after),
            before_lines=before_lines,
            after_lines=after_lines,
            occurrences=before.count(action.old) if action.old else 1,
            applied=True,
            bytecode_purged=purged,
        )
        self._note_edit(action.path)
        return diff

    def _git_stage_note(self, paths: Sequence[str]) -> str:
        """git-module staging when its API exists; else the record trail.

        The nexus git seat is a phase-15 placeholder (no API yet), so
        the honest answer is ``recorded`` — the diff trail above IS
        the record. The day the module grows ``stage``, this flips.
        """
        if not paths:
            return "recorded"
        try:
            module = importlib.import_module("nexus.git")
        except Exception:  # noqa: BLE001 — availability probe
            return "recorded"
        stage = getattr(module, "stage", None)
        if callable(stage):
            try:
                stage(str(self._root), list(paths))
                return "staged"
            except Exception:  # noqa: BLE001 — staging must never kill the edit
                return "recorded"
        return "recorded"

    # ----------------------------------------------------------- §15.1 run

    def run(self, request: OperationRequest) -> OperationResult:
        """run — one argv command, timeout, captured honest output."""
        started = time.perf_counter()
        command = [str(part) for part in request.payload.get("command") or ()]
        if not command:
            return OperationResult.fail_result(
                CodingOperationKind.RUN,
                (time.perf_counter() - started) * 1000.0,
                "no command supplied",
                "payload['command'] must be a non-empty argv list",
            )
        cwd = str(self._root) if str(self._root) else None
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=float(request.timeout_s),
            )
            outcome = RunOutcome(
                command=tuple(command),
                exit_code=proc.returncode,
                stdout=_tail(proc.stdout),
                stderr=_tail(proc.stderr),
            )
            status = OperationStatus.OK if proc.returncode == 0 else OperationStatus.FAIL
            return OperationResult(
                kind=CodingOperationKind.RUN,
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
                summary=f"exit {proc.returncode}: {' '.join(command)}",
                error="" if proc.returncode == 0 else _tail(proc.stderr, 500),
                payload=outcome.to_dict(),
            )
        except subprocess.TimeoutExpired as exc:
            outcome = RunOutcome(
                command=tuple(command),
                timed_out=True,
                stdout=_tail(str(exc.stdout or "")),
                stderr=_tail(str(exc.stderr or "")),
            )
            return OperationResult.fail_result(
                CodingOperationKind.RUN,
                (time.perf_counter() - started) * 1000.0,
                f"timeout after {request.timeout_s}s: {' '.join(command)}",
                f"TimeoutExpired: {request.timeout_s}s",
                outcome.to_dict(),
            )
        except OSError as exc:
            return OperationResult.fail_result(
                CodingOperationKind.RUN,
                (time.perf_counter() - started) * 1000.0,
                f"cannot run: {' '.join(command)}",
                f"{type(exc).__name__}: {exc}",
            )

    # ---------------------------------------------------------- §15.1 test

    def test(self, request: OperationRequest) -> OperationResult:
        """test — the real harness runner if importable, else pytest."""
        started = time.perf_counter()
        target = str(request.payload.get("target") or self._root)
        harness = _find_harness_runner()
        outcome: TestOutcome | None = None
        if harness is not None:
            outcome = _harness_run(harness[1], target)
        if outcome is None:
            outcome = self._pytest(target, request.timeout_s)
        status = OperationStatus.OK if outcome.exit_code == 0 else OperationStatus.FAIL
        return OperationResult(
            kind=CodingOperationKind.TEST,
            status=status,
            duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
            summary=(
                f"{outcome.passed} passed, {outcome.failed} failed "
                f"(exit {outcome.exit_code}, {outcome.runner})"
            ),
            error="" if outcome.exit_code == 0 else "; ".join(outcome.failing_tests)[:500],
            payload=outcome.to_dict(),
        )

    def _pytest(self, target: str, timeout_s: float) -> TestOutcome:
        """The honest fallback: ``python -m pytest <target> -q``."""
        command = [
            sys.executable,
            "-m",
            "pytest",
            target,
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "--tb=short",
        ]
        try:
            proc = subprocess.run(
                command,
                cwd=str(self._root) if str(self._root) else None,
                capture_output=True,
                text=True,
                timeout=float(timeout_s),
            )
        except subprocess.TimeoutExpired:
            return TestOutcome(
                command=tuple(command),
                target=target,
                runner="pytest",
                exit_code=-1,
                stderr_tail=f"TimeoutExpired: {timeout_s}s",
            )
        passed, failed, failing = _parse_pytest_output(proc.stdout, proc.returncode)
        return TestOutcome(
            command=tuple(command),
            target=target,
            runner="pytest",
            exit_code=proc.returncode,
            passed=passed,
            failed=failed,
            failing_tests=failing,
            stdout_tail=_tail(proc.stdout),
            stderr_tail=_tail(proc.stderr),
        )

    # --------------------------------------------------------- §15.1 debug

    def debug(self, request: OperationRequest) -> OperationResult:
        """debug — failing tests + stderr + §13 lessons → findings."""
        started = time.perf_counter()
        payload = request.payload
        test_outcome = dict(payload.get("test_outcome") or {})
        failing = [str(t) for t in payload.get("failing_tests") or ()]
        if not failing and test_outcome:
            failing = [str(t) for t in test_outcome.get("failing_tests") or ()]
        stderr = str(payload.get("stderr") or test_outcome.get("stderr_tail") or "")
        stdout = str(payload.get("stdout") or test_outcome.get("stdout_tail") or "")
        fixes = parse_edit_actions(payload.get("fixes") or ())

        lesson_texts: list[str] = []
        if self._learning_store is not None and failing:
            query = " ".join(failing) + " " + request.goal
            try:
                lesson_texts = [
                    record.lesson
                    for record in self._learning_store.search_lessons(query, limit=3)
                ]
            except Exception:  # noqa: BLE001 — lesson recall must not kill debug
                lesson_texts = []

        findings: list[DebugFinding] = []
        for index, node_id in enumerate(failing):
            evidence = _evidence_for(node_id, stderr, stdout)
            hypothesis = _hypothesis(node_id, evidence)
            findings.append(
                DebugFinding(
                    test=node_id,
                    hypothesis=hypothesis,
                    evidence=tuple(evidence),
                    suggested_fix=fixes[index] if index < len(fixes) else None,
                    lessons=tuple(lesson_texts),
                )
            )
        if not findings:
            findings.append(
                DebugFinding(
                    test="(no failing test named)",
                    hypothesis=(
                        "the suite fails without a named test — inspect the "
                        "collection error in the captured output"
                    ),
                    evidence=tuple(
                        line for line in stderr.splitlines()[-5:] if line.strip()
                    ),
                    lessons=tuple(lesson_texts),
                )
            )
        outcome = DebugOutcome(
            findings=tuple(findings),
            lessons_consulted=len(lesson_texts),
            fixes_available=len(fixes),
        )
        return OperationResult.ok_result(
            CodingOperationKind.DEBUG,
            (time.perf_counter() - started) * 1000.0,
            f"{len(findings)} finding(s), {len(lesson_texts)} lesson(s) consulted",
            outcome.to_dict(),
        )

    # -------------------------------------------------------- §15.1 review

    def review(self, request: OperationRequest) -> OperationResult:
        """review — re-run tests, check the diff trail, render the verdict."""
        started = time.perf_counter()
        payload = request.payload
        edits_applied = int(payload.get("edits_applied") or 0)
        debug_cycles = int(payload.get("debug_cycles") or 0)
        max_cycles = int(payload.get("max_debug_cycles") or 3)
        supplied = dict(payload.get("test_outcome") or {})
        if supplied:
            outcome_dict = supplied
            re_ran = False
        else:
            test_result = self.test(
                OperationRequest(
                    kind=CodingOperationKind.TEST,
                    goal=request.goal,
                    workspace_root=str(self._root),
                    timeout_s=request.timeout_s,
                )
            )
            outcome_dict = dict(test_result.payload)
            re_ran = True
        tests_green = (
            int(outcome_dict.get("exit_code", -1)) == 0
            and int(outcome_dict.get("failed", 1)) == 0
            and int(outcome_dict.get("passed", 0)) > 0
        )
        outstanding = tuple(outcome_dict.get("failing_tests") or ())
        checks = (
            ReviewCheck(
                name="tests_green",
                passed=tests_green,
                detail=(
                    f"{outcome_dict.get('passed', 0)} passed, "
                    f"{outcome_dict.get('failed', 0)} failed"
                    + (" (re-run by review)" if re_ran else "")
                ),
            ),
            ReviewCheck(
                name="edits_applied",
                # A proof task ("prove the project green") edits nothing —
                # green tests ARE the deliverable; a fix task must edit.
                passed=edits_applied > 0 or tests_green,
                detail=(
                    f"{edits_applied} edit(s) on disk"
                    if edits_applied > 0
                    else (
                        "proof task — tests already green, no edits required"
                        if tests_green
                        else "no edits applied and tests red"
                    )
                ),
            ),
            ReviewCheck(
                name="no_outstanding_failures",
                passed=not outstanding,
                detail=(
                    "no failing tests remain"
                    if not outstanding
                    else f"failing: {', '.join(outstanding)}"
                ),
            ),
            ReviewCheck(
                name="debug_cycles_bounded",
                passed=debug_cycles <= max_cycles,
                detail=f"{debug_cycles} debug cycle(s) of {max_cycles} allowed",
            ),
        )
        approved = all(check.passed for check in checks)
        reasons = tuple(
            f"{'PASS' if check.passed else 'FAIL'} {check.name} — {check.detail}"
            for check in checks
        )
        verdict = ReviewVerdict(
            approved=approved,
            reasons=reasons + (
                (f"VERDICT approved — goal: {request.goal}",)
                if approved
                else (f"VERDICT rejected — goal: {request.goal}",)
            ),
            checks=checks,
        )
        outcome = ReviewOutcome(
            verdict=verdict,
            tests_passed=tests_green,
            edits_applied=edits_applied,
            debug_cycles=debug_cycles,
        )
        return OperationResult.ok_result(
            CodingOperationKind.REVIEW,
            (time.perf_counter() - started) * 1000.0,
            "approved" if approved else "rejected",
            outcome.to_dict(),
        )

    # -------------------------------------------------------- session notes

    def _note_read(self, path: str) -> None:
        if self._session is not None:
            self._session.note_read(path)

    def _note_edit(self, path: str) -> None:
        if self._session is not None:
            self._session.note_edit(path)

    def _note_tool_call(self, request: OperationRequest, result: OperationResult) -> None:
        if self._session is not None:
            self._session.note_tool_call(
                ToolCallRecord(
                    name=f"coding.{request.kind.value}",
                    detail=result.summary[:200],
                    ok=result.ok,
                    duration_ms=result.duration_ms,
                )
            )


def _evidence_for(node_id: str, stderr: str, stdout: str) -> list[str]:
    """The output lines that mention the failing test (or the assert tail)."""
    test_name = node_id.split("::")[-1]
    mentions = [
        line.strip()
        for line in (stderr + "\n" + stdout).splitlines()
        if test_name in line or node_id in line
    ]
    if mentions:
        return mentions[:5]
    return [line.strip() for line in stderr.splitlines()[-5:] if line.strip()][:5]


def _hypothesis(node_id: str, evidence: Sequence[str]) -> str:
    """One deterministic hypothesis per finding — from its own words."""
    source = _source_file_for_test(node_id)
    for line in evidence:
        lowered = line.lower()
        if "assert" in lowered:
            return (
                f"{node_id} fails on an assertion ({line.strip()[:120]}); "
                f"the expectation in {source} disagrees with the code's result"
            )
        if "error" in lowered or "exception" in lowered or "traceback" in lowered:
            return (
                f"{node_id} raises before asserting ({line.strip()[:120]}); "
                f"inspect {source} for the raising path"
            )
    return (
        f"{node_id} fails without an assertion line in the captured output; "
        f"start at {source} and re-run the test for the full traceback"
    )
