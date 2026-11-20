"""Repository Lifecycle (New Plan §16.3) — eight stages, one honest report.

The §16.3 pipeline, verbatim::

    Discover → Clone → Index → Modify → Test → Commit → Review → Push

This is the loop that makes GitHub part of the runtime (the §16 thesis):
a repository enters NEXUS as a *candidate*, and leaves as *pushed work*
— or the report says exactly which stage failed and why.  Every stage
publishes canonical §2.2 tool events; every answer is a
:class:`~nexus.git.contracts.LifecycleReport` whose ``reached`` property
never lies.

Stage contracts:

* ``discover``  — a provider callable returns one
  :class:`~nexus.github.contracts.SearchCandidate` (or an equivalent
  mapping with ``clone_url``).  In tests this is a local provider; in
  production it is the §16.2 GitHub search.
* ``clone``     — the real GitEngine clone into the workspace root.
* ``index``     — a light file/stack index (§125's *Clone → Detect
  stack → Index files* rung).  An ``indexer`` hook can deepen it with
  the §14 code-intelligence engine — the lifecycle does not require it.
* ``modify``    — a ``modifier`` callable receives the engine and edits
  files; its returned trail (files touched) feeds the review.
* ``test``      — one whitelisted test command run in the repo
  (``allowlist`` — by default pytest and no-ops); the exit code decides.
* ``commit``    — a real commit with a conventional message.
* ``review``    — a ``reviewer`` callable sees the diff summary, the
  modify trail and the test outcome, and must approve; a rejection
  stops the pipeline with ``ReviewRejectedError`` — never a spin.
* ``push``      — a real push to the discovered remote through the
  GitHub engine (or an explicitly injected local origin for tests).

دورة المستودع — ثماني مراحل بحكم صادق لكل مرحلة، والرفض يقف لا يدور.

Stdlib only.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexus.events import EventName

from .contracts import (
    LIFECYCLE_STAGES,
    LifecycleError,
    LifecycleReport,
    ReviewRejectedError,
    StageResult,
    StageState,
    utc_now_iso,
)

#: The only test commands the lifecycle will run by default.  Anything
#: else must be explicitly whitelisted by the caller (never shell, never
#: rm-style commands).
_DEFAULT_TEST_ALLOWLIST: tuple[str, ...] = (
    "pytest",
    "python -m pytest",
    "python -m unittest",
)

#: Commands that may never ride the test stage, even if whitelisted.
_FORBIDDEN_TEST_PREFIXES: tuple[str, ...] = (
    "rm ",
    "del ",
    "format ",
    "shutdown",
    "git push",
    "curl",
    "wget",
    "mv ",
)

LifecycleMod = Callable[[Any], Sequence[str]]
LifecycleReviewer = Callable[[Mapping[str, Any]], bool]
LifecycleDiscover = Callable[[], Mapping[str, Any]]
LifecycleIndexer = Callable[[Any], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class StackFacts:
    """The §125 detect-stack rung — honest facts from real file names."""

    languages: tuple[str, ...]
    file_count: int
    entry_points: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "languages": list(self.languages),
            "file_count": self.file_count,
            "entry_points": list(self.entry_points),
        }


_STACK_MARKERS: tuple[tuple[str, str], ...] = (
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("requirements.txt", "python"),
    ("package.json", "javascript"),
    ("tsconfig.json", "typescript"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("*.csproj", "csharp"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
)

_ENTRY_MARKERS: tuple[str, ...] = (
    "main.py",
    "__main__.py",
    "main.go",
    "main.rs",
    "index.js",
    "index.ts",
    "Program.cs",
)


def detect_stack(root: Path) -> StackFacts:
    """Real file-name facts — no guessing, no network."""
    languages: list[str] = []
    for marker, lang in _STACK_MARKERS:
        if marker.startswith("*"):
            if list(root.glob(marker)):
                languages.append(lang)
        elif (root / marker).exists():
            languages.append(lang)
    file_count = sum(1 for _ in root.rglob("*") if _.is_file())
    entries = tuple(
        name
        for name in _ENTRY_MARKERS
        if any(p.name == name for p in root.rglob(name))
    )[:8]
    return StackFacts(
        languages=tuple(dict.fromkeys(languages)),
        file_count=file_count,
        entry_points=entries,
    )


class RepoLifecycle:
    """The §16.3 pipeline — drive one repository through the eight stages.

    ``discover``, ``modifier``, ``reviewer`` and ``indexer`` are callables
    (injected so tests can run the *full* pipeline with a local bare
    origin and no network).  ``pusher`` defaults to the GitHub engine's
    ``push``; tests inject a local push.
    """

    source_name = "nexus.git.lifecycle"

    def __init__(
        self,
        git_engine_cls: type,
        *,
        workspace_root: Path | str,
        discover: LifecycleDiscover | None = None,
        modifier: LifecycleMod | None = None,
        reviewer: LifecycleReviewer | None = None,
        indexer: LifecycleIndexer | None = None,
        pusher: Callable[[Any, str], Any] | None = None,
        test_command: str | None = "pytest",
        test_allowlist: Sequence[str] = _DEFAULT_TEST_ALLOWLIST,
        branch: str | None = None,
        bus: Any = None,
    ) -> None:
        self._engine_cls = git_engine_cls
        self._root = Path(workspace_root)
        self._discover = discover
        self._modifier = modifier
        self._reviewer = reviewer
        self._indexer = indexer
        self._pusher = pusher
        self._test_command = (test_command or "").strip()
        self._allowlist = tuple(test_allowlist)
        self._branch = branch
        self._bus = bus

    # ------------------------------------------------------------ plumbing

    def _emit(self, name: EventName, payload: dict[str, Any], ok: bool = True) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            EventName.TOOL_COMPLETED if ok else EventName.TOOL_FAILED,
            payload=payload,
            source=self.source_name,
        )

    def _check_test_command(self) -> tuple[str, ...]:
        if not self._test_command:
            raise LifecycleError("the test stage needs a test command")
        for forbidden in _FORBIDDEN_TEST_PREFIXES:
            if self._test_command.lower().startswith(forbidden):
                raise LifecycleError(f"forbidden test command: {self._test_command!r}")
        if self._test_command not in self._allowlist:
            raise LifecycleError(
                f"test command not whitelisted: {self._test_command!r} "
                f"(allowed: {list(self._allowlist)})"
            )
        return tuple(self._test_command.split())

    @staticmethod
    def _candidate_url(candidate: Mapping[str, Any]) -> str:
        url = candidate.get("clone_url") or candidate.get("url")
        if not url:
            raise LifecycleError("the discovered candidate carries no clone_url")
        return str(url)

    # ------------------------------------------------------------ the loop

    def run(self, *, skip_push: bool = False) -> LifecycleReport:
        """Run the eight stages in order, stopping at the first failure."""
        report = LifecycleReport(started_at=utc_now_iso())
        results: dict[str, StageResult] = {}
        for name in LIFECYCLE_STAGES:
            results[name] = StageResult(stage=name)
            report.stages.append(results[name])

        engine: Any = None
        candidate: Mapping[str, Any] | None = None
        trail: tuple[str, ...] = ()
        commit_result: Any = None
        current_stage: StageResult | None = None

        try:
            # ------------------------------------------------ discover
            stage = results["discover"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            if self._discover is None:
                stage.mark(StageState.FAILED, "no discover provider")
                raise LifecycleError("no discover provider")
            candidate = dict(self._discover())
            stage.data["candidate"] = {
                k: v for k, v in candidate.items()
                if k in ("name", "owner", "clone_url", "stars", "license")
            }
            stage.mark(StageState.OK, str(candidate.get("name", "")))
            self._emit(
                EventName.TOOL_COMPLETED, {"tool": "lifecycle.discover", "name": stage.detail}
            )

            # -------------------------------------------------- clone
            stage = results["clone"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            url = self._candidate_url(candidate)
            dest = self._root / str(candidate.get("name") or "repo")
            engine = self._engine_cls.clone(url, dest, bus=self._bus)
            report.repo_path = str(dest.resolve())
            stage.data["path"] = report.repo_path
            stage.mark(StageState.OK, url)
            self._emit(
                EventName.TOOL_COMPLETED, {"tool": "lifecycle.clone", "path": report.repo_path}
            )

            # -------------------------------------------------- index
            stage = results["index"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            facts = detect_stack(dest)
            stage.data["stack"] = facts.as_dict()
            if self._indexer is not None:
                deep = self._indexer(engine)
                stage.data["deep"] = dict(deep)
            stage.mark(StageState.OK, ",".join(facts.languages) or "unknown")
            self._emit(EventName.TOOL_COMPLETED, {"tool": "lifecycle.index", "stack": stage.detail})

            # ------------------------------------------------- modify
            stage = results["modify"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            if self._modifier is None:
                stage.mark(StageState.SKIPPED, "no modifier — lifecycle as clean audit")
            else:
                touched = self._modifier(engine)
                trail = tuple(touched)
                stage.data["files"] = list(trail)
                stage.mark(StageState.OK, f"{len(trail)} file(s)")
                self._emit(
                    EventName.TOOL_COMPLETED, {"tool": "lifecycle.modify", "files": len(trail)}
                )

            # --------------------------------------------------- test
            stage = results["test"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            if not self._test_command:
                stage.mark(StageState.SKIPPED, "no test command configured")
            else:
                argv = self._check_test_command()
                has_pytest_files = (
                    (dest / "tests").exists()
                    or (dest / "test").exists()
                    or any(dest.glob("test_*.py"))
                )
                if not has_pytest_files:
                    stage.mark(StageState.SKIPPED, "no test suite detected in the repository")
                else:
                    proc = subprocess.run(
                        argv,
                        cwd=str(dest),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=600,
                        check=False,
                    )
                    stage.data["exit_code"] = proc.returncode
                    stage.data["tail"] = (proc.stdout or proc.stderr)[-800:]
                    if proc.returncode != 0:
                        stage.mark(StageState.FAILED, f"exit {proc.returncode}")
                        self._emit(
                            EventName.TOOL_FAILED,
                            {"tool": "lifecycle.test", "exit": proc.returncode},
                            ok=False,
                        )
                        raise LifecycleError(f"the test stage failed (exit {proc.returncode})")
                    stage.mark(StageState.OK, f"exit {proc.returncode}")
                    self._emit(EventName.TOOL_COMPLETED, {"tool": "lifecycle.test", "exit": 0})

            # ------------------------------------------------- commit
            stage = results["commit"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            engine.stage(".")
            if engine.is_clean():
                stage.mark(StageState.SKIPPED, "nothing to commit")
            else:
                commit_result = engine.commit(
                    f"feat(lifecycle): {candidate.get('name', 'repo')} — "
                    f"modify stage trail ({len(trail)} files)"
                )
                stage.data["sha"] = commit_result.short_sha
                stage.mark(StageState.OK, commit_result.short_sha)
                self._emit(
                    EventName.TOOL_COMPLETED,
                    {"tool": "lifecycle.commit", "sha": commit_result.short_sha},
                )

            # ------------------------------------------------- review
            stage = results["review"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            diff = engine.diff(ref="HEAD~1") if engine.head() else engine.diff()
            bundle: dict[str, Any] = {
                "diff": diff.as_dict(),
                "trail": list(trail),
                "test": results["test"].as_dict(),
                "stack": results["index"].data.get("stack", {}),
            }
            stage.data["review_bundle"] = bundle
            if self._reviewer is None:
                stage.mark(StageState.SKIPPED, "no reviewer — review gate disabled by caller")
            else:
                approved = bool(self._reviewer(bundle))
                if not approved:
                    stage.mark(StageState.FAILED, "reviewer rejected")
                    self._emit(
                        EventName.TOOL_FAILED,
                        {"tool": "lifecycle.review", "approved": False},
                        ok=False,
                    )
                    raise ReviewRejectedError(
                        "the review stage rejected the work — pipeline stopped"
                    )
                stage.mark(StageState.OK, "approved")
                self._emit(EventName.TOOL_COMPLETED, {"tool": "lifecycle.review", "approved": True})

            # --------------------------------------------------- push
            stage = results["push"]
            current_stage = stage
            stage.started_at = utc_now_iso()
            if skip_push:
                stage.mark(StageState.SKIPPED, "skip_push requested")
            else:
                if self._pusher is not None:
                    # None branch = push the tree's *current* branch — the
                    # honest default for repositories whose default branch
                    # is master, trunk, or anything else.
                    self._pusher(engine, self._branch or engine.current_branch())
                else:
                    raise LifecycleError(
                        "no pusher — pass a GitHub engine or an explicit local pusher "
                        "(never guess a remote)"
                    )
                stage.mark(StageState.OK, f"branch {self._branch or engine.current_branch()}")
                self._emit(
                    EventName.TOOL_COMPLETED,
                    {"tool": "lifecycle.push", "branch": self._branch or engine.current_branch()},
                )

        except Exception as exc:  # noqa: BLE001 — the report *is* the error surface
            # A stage that started but never finished is the failing stage —
            # the report must say so explicitly (never a silent PENDING).
            if current_stage is not None and current_stage.state is StageState.PENDING:
                current_stage.mark(StageState.FAILED, str(exc)[:300])
            report.finished_at = utc_now_iso()
            self._emit(
                EventName.TOOL_FAILED,
                {"tool": "lifecycle.run", "reached": report.reached, "error": str(exc)},
                ok=False,
            )
            return report

        report.finished_at = utc_now_iso()
        self._emit(EventName.TOOL_COMPLETED, {"tool": "lifecycle.run", "reached": report.reached})
        return report
