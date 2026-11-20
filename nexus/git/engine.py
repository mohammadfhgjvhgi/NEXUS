"""The Git Engine (New Plan §16.1) — eight operations over the real binary.

Design law (all from the New Plan):

* NEXUS owns the git semantics (§61): one engine class, eight operations,
  honest errors — the underlying ``git`` binary is an implementation
  detail behind this surface.
* The Core stays stdlib-only (Plan §2): no git-python, no dulwich — the
  real ``git`` executable is driven through a bounded subprocess surface
  and its absence is reported honestly (``GitBinaryMissingError``).
* The binary is the judge (the Speed Rules): every answer below comes
  from real ``git`` output, never from a guessed model of it.
* Only canonical §2.2 events are published (tool.called/tool.completed/
  tool.failed) with git operation names — never raw secret payloads.

محرك Git الحقيقي — ثماني عمليات على الثنائية الفعلية، غيابها يُعلن
بصدق، وأحداثها كنسية فقط، وكل جواب من خرج الثنائية لا من تخمين.

Stdlib only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from nexus.events import EventName

from .contracts import (
    BranchRef,
    CommitResult,
    DiffSummary,
    GitBinaryMissingError,
    GitEngineError,
    InvalidRepoError,
    MergeConflictError,
    MergeResult,
    RollbackResult,
    StatusReport,
    TagRecord,
    WorktreeEntry,
)

_GIT_TIMEOUT = 60
_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")

# A clean, deterministic environment: no prompt, no pager, no locale
# drift, no credential helper surprise.  Windows-safe by construction.
_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PAGER": "cat",
    "PAGER": "cat",
    "GIT_EDITOR": ":",
    "VISUAL": ":",
    "LC_ALL": "C",
}

#: The repo-local identity the engine provisions when the host resolves
#: none (fresh CI runners, fresh clones).  Repo-local only — never global,
#: never overriding an existing identity.
_IDENTITY_NAME = "NEXUS"
_IDENTITY_EMAIL = "nexus@nexus.local"


class GitEngine:
    """The §16.1 engine — ``status diff branch worktree commit merge tag
    rollback`` over one real repository path.

    ``bus`` (an :class:`~nexus.events.EventBus`) is optional; when given,
    every operation publishes its canonical tool events with source
    ``nexus.git``.
    """

    source_name = "nexus.git"

    def __init__(self, repo: Path | str, bus: Any = None, git_executable: str = "git") -> None:
        self.repo = Path(repo).resolve()
        self._bus = bus
        self._git = git_executable
        if shutil.which(self._git) is None:
            raise GitBinaryMissingError(
                f"the git executable {self._git!r} was not found on PATH"
            )

    # ------------------------------------------------------------ plumbing

    def _emit(self, name: EventName, payload: dict[str, Any], ok: bool = True) -> None:
        if self._bus is None:
            return
        event = EventName.TOOL_COMPLETED if ok else EventName.TOOL_FAILED
        self._bus.publish(
            event,
            payload=payload,
            source=self.source_name,
        )

    def _run(self, *args: str, cwd: Path | None = None, timeout: int = _GIT_TIMEOUT) -> str:
        """One bounded git invocation — stdout back, stderr raises honestly."""
        argv = [self._git, *args]
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd if cwd is not None else self.repo),
                env=_ENV,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:  # pragma: no cover - guarded in __init__
            raise GitBinaryMissingError(str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise GitEngineError(f"git timed out after {timeout}s: {' '.join(args)}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise GitEngineError(f"git {' '.join(args)} failed ({proc.returncode}): {detail}")
        return proc.stdout

    def _require_repo(self) -> None:
        if not self.repo.exists():
            raise InvalidRepoError(f"repository path does not exist: {self.repo}")
        probe = subprocess.run(
            [self._git, "rev-parse", "--is-inside-work-tree"],
            cwd=str(self.repo),
            env=_ENV,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            raise InvalidRepoError(f"not a git work tree: {self.repo}")

    @staticmethod
    def _short(sha: str) -> str:
        return sha[:12]

    # -------------------------------------------------------------- status

    def status(self) -> StatusReport:
        """``status`` — branch, divergence and the three file buckets."""
        self._require_repo()
        self._emit(EventName.TOOL_CALLED, {"tool": "git.status"})
        binfo = self._run("status", "--porcelain=v2", "--branch")
        branch, head_sha, ahead, behind = "HEAD", "", 0, 0
        staged: list[str] = []
        modified: list[str] = []
        untracked: list[str] = []
        for line in binfo.splitlines():
            if line.startswith("# branch.head "):
                branch = line.split(" ", 2)[2]
            elif line.startswith("# branch.oid "):
                head_sha = line.split(" ", 2)[2]
            elif line.startswith("# branch.ab "):
                parts = line.split()
                ahead, behind = abs(int(parts[2])), abs(int(parts[3]))
            elif line.startswith("1 ") or line.startswith("2 "):
                fields = line.split(None, 8)
                xy = fields[1]
                path = fields[-1].split("\t")[-1]  # renames: "new\told"
                if xy[0] != ".":
                    staged.append(path)
                if xy[1] != ".":
                    modified.append(path)
            elif line.startswith("? "):
                untracked.append(line[2:].strip())
        report = StatusReport(
            branch=branch,
            head_sha=head_sha,
            clean=not (staged or modified or untracked),
            staged=tuple(staged),
            modified=tuple(modified),
            untracked=tuple(untracked),
            ahead=ahead,
            behind=behind,
        )
        self._emit(EventName.TOOL_COMPLETED, {"tool": "git.status", "clean": report.clean})
        return report

    # ---------------------------------------------------------------- diff

    def diff(
        self,
        *,
        staged: bool = False,
        ref: str | None = None,
        with_patch: bool = False,
    ) -> DiffSummary:
        """``diff`` — which files, how many lines; patch optional.

        ``git diff`` never reports untracked files — so the engine adds
        them explicitly (their real line counts as insertions).  A diff
        that hides new files would lie to the review stage.
        """
        self._require_repo()
        self._emit(EventName.TOOL_CALLED, {"tool": "git.diff"})
        num_args = ["diff", "--numstat"]
        if staged:
            num_args.append("--cached")
        if ref:
            num_args.append(ref)
        numstat = self._run(*num_args)
        files: list[str] = []
        insertions = 0
        deletions = 0
        for line in numstat.splitlines():
            if not line.strip():
                continue
            add, rem, path = line.split("\t", 2)
            files.append(path)
            insertions += int(add) if add.isdigit() else 0
            deletions += int(rem) if rem.isdigit() else 0
        if not ref and not staged:
            for path in self.status().untracked:
                real = self.repo / path
                lines = 0
                if real.is_file():
                    try:
                        lines = sum(1 for _ in real.open("rb"))
                    except OSError:
                        lines = 0
                files.append(path)
                insertions += lines
        patch = ""
        if with_patch:
            patch_args = ["diff"]
            if staged:
                patch_args.append("--cached")
            if ref:
                patch_args.append(ref)
            patch = self._run(*patch_args)
        summary = DiffSummary(
            files=tuple(files),
            insertions=insertions,
            deletions=deletions,
            patch=patch,
        )
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "git.diff", "files": len(files),
             "insertions": insertions, "deletions": deletions},
        )
        return summary

    # -------------------------------------------------------------- branch

    def branches(self) -> tuple[BranchRef, ...]:
        """``branch`` (read) — every local branch with its commit."""
        self._require_repo()
        self._emit(EventName.TOOL_CALLED, {"tool": "git.branch"})
        out = self._run(
            "for-each-ref", "--format=%(refname:short)|%(objectname)|%(HEAD)", "refs/heads/"
        )
        refs: list[BranchRef] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            name, sha, marker = line.split("|")
            refs.append(BranchRef(name=name, current=marker.strip() == "*", commit=sha))
        self._emit(EventName.TOOL_COMPLETED, {"tool": "git.branch", "count": len(refs)})
        return tuple(refs)

    def current_branch(self) -> str:
        out = self._run("rev-parse", "--abbrev-ref", "HEAD")
        return out.strip()

    def head(self) -> str:
        """The full HEAD sha — '' when the repo has no commit yet."""
        try:
            return self._run("rev-parse", "HEAD").strip()
        except GitEngineError:
            return ""

    def create_branch(
        self, name: str, *, checkout: bool = True, from_ref: str | None = None
    ) -> BranchRef:
        """``branch`` (write) — create (and optionally switch) a branch."""
        self._require_repo()
        if not name or not re.fullmatch(r"[A-Za-z0-9._/\-]+", name):
            raise GitEngineError(f"invalid branch name: {name!r}")
        self._emit(EventName.TOOL_CALLED, {"tool": "git.branch.create", "branch": name})
        if from_ref:
            if checkout:
                self._run("checkout", "-b", name, from_ref)
            else:
                self._run("branch", name, from_ref)
        else:
            self._run("checkout", "-b", name) if checkout else self._run("branch", name)
        sha = self.head()
        ref = BranchRef(name=name, current=checkout, commit=sha)
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "git.branch.create", "branch": name, "sha": sha}
        )
        return ref

    def checkout(self, ref: str) -> str:
        """Switch the work tree to ``ref``; refuses to lose dirty work."""
        self._require_repo()
        status = self.status()
        if not status.clean:
            raise GitEngineError(
                "refusing to checkout with uncommitted changes (use commit or rollback first)"
            )
        self._run("checkout", ref)
        sha = self.head()
        self._emit(EventName.TOOL_COMPLETED, {"tool": "git.checkout", "ref": ref, "sha": sha})
        return sha

    # ------------------------------------------------------------ worktree

    def worktrees(self) -> tuple[WorktreeEntry, ...]:
        """``worktree`` (read) — the main tree plus every linked one."""
        self._require_repo()
        self._emit(EventName.TOOL_CALLED, {"tool": "git.worktree"})
        out = self._run("worktree", "list", "--porcelain")
        entries: list[WorktreeEntry] = []
        current: dict[str, Any] = {}
        for line in out.splitlines():
            if line.startswith("worktree "):
                if current:
                    entries.append(self._worktree_entry(current))
                    current = {}
                # git prints native paths with '/' on Windows — normalize so
                # every engine API speaks one path dialect per platform
                current["path"] = str(Path(line[len("worktree "):]))
            elif line.startswith("HEAD "):
                current["head"] = line[len("HEAD "):]
            elif line.startswith("branch "):
                current["branch"] = line[len("branch "):]
            elif line == "bare":
                current["bare"] = True
            elif line == "detached":
                current["detached"] = True
        if current:
            entries.append(self._worktree_entry(current))
        self._emit(EventName.TOOL_COMPLETED, {"tool": "git.worktree", "count": len(entries)})
        return tuple(entries)

    @staticmethod
    def _worktree_entry(raw: dict[str, Any]) -> WorktreeEntry:
        branch = raw.get("branch")
        if branch:
            branch = branch.removeprefix("refs/heads/")
        return WorktreeEntry(
            path=raw["path"],
            head=raw.get("head", ""),
            branch=branch,
            bare=bool(raw.get("bare")),
            detached=bool(raw.get("detached")),
        )

    def add_worktree(
        self, path: Path | str, *, branch: str | None = None, new_branch: str | None = None
    ) -> WorktreeEntry:
        """``worktree`` (write) — a linked tree for one parallel agent."""
        self._require_repo()
        target = Path(path)
        if target.exists() and any(target.iterdir()):
            raise GitEngineError(f"worktree path must be empty or absent: {target}")
        args = ["worktree", "add"]
        if new_branch:
            args += ["-b", new_branch]
        # git's grammar: worktree add [-b <new>] <path> [<commit-ish>]
        args.append(str(target))
        if branch:
            args.append(branch)
        self._run(*args)
        sha = self.head()
        entry = WorktreeEntry(
            path=str(target.resolve()),
            head=sha,
            branch=new_branch or branch,
        )
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "git.worktree.add", "path": entry.path, "branch": entry.branch},
        )
        return entry

    def remove_worktree(self, path: Path | str, *, force: bool = False) -> str:
        """``worktree`` (teardown) — remove one linked tree."""
        self._require_repo()
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(Path(path).resolve()))
        self._run(*args)
        self._emit(EventName.TOOL_COMPLETED, {"tool": "git.worktree.remove", "path": str(path)})
        return str(path)

    # -------------------------------------------------------------- commit

    def stage(self, *paths: str) -> tuple[str, ...]:
        """Stage files (or everything with ``.``) before commit."""
        self._require_repo()
        if not paths:
            raise GitEngineError("stage() needs at least one path ('.' for all)")
        for path in paths:
            self._run("add", "--", path)
        return tuple(paths)

    def _ensure_identity(self) -> None:
        """A fresh CI runner or a fresh clone resolves no git identity —
        the commit would die with ``Author identity unknown``.  Provision
        a repo-local NEXUS identity once, only when none resolves; never
        global, never overriding an existing one."""
        probe = subprocess.run(
            [self._git, "config", "user.email"],
            cwd=str(self.repo),
            env=_ENV,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if not (probe.stdout or "").strip():
            self._run("config", "user.name", _IDENTITY_NAME)
            self._run("config", "user.email", _IDENTITY_EMAIL)

    def commit(
        self,
        message: str,
        *,
        paths: tuple[str, ...] | None = None,
        allow_empty: bool = False,
    ) -> CommitResult:
        """``commit`` — a real commit with a real message; nothing faked."""
        self._require_repo()
        self._ensure_identity()
        if not message or not message.strip():
            raise GitEngineError("a commit message is required")
        self._emit(EventName.TOOL_CALLED, {"tool": "git.commit"})
        if paths:
            self.stage(*paths)
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        self._run(*args)
        sha = self.head()
        files = tuple(self._run("show", "--name-only", "--format=", "HEAD").split())
        result = CommitResult(sha=sha, short_sha=self._short(sha), message=message, files=files)
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "git.commit", "sha": result.short_sha, "files": len(files)},
        )
        return result

    # --------------------------------------------------------------- merge

    def merge(self, branch: str) -> MergeResult:
        """``merge`` — fast-forward or merge-commit; conflicts surface honestly."""
        self._require_repo()
        # a non-fast-forward merge writes a merge commit — identity must resolve
        self._ensure_identity()
        self._emit(EventName.TOOL_CALLED, {"tool": "git.merge", "branch": branch})
        proc = subprocess.run(
            [self._git, "merge", "--no-edit", branch],
            cwd=str(self.repo),
            env=_ENV,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if proc.returncode == 0:
            out = proc.stdout
            fast_forward = "Fast-forward" in out or "fast-forward" in out.lower()
            result = MergeResult(merged=True, fast_forward=fast_forward, sha=self.head())
            self._emit(
                EventName.TOOL_COMPLETED,
                {"tool": "git.merge", "branch": branch, "fast_forward": fast_forward},
            )
            return result
        conflicted = tuple(
            line.split(":", 1)[-1].strip()
            for line in (proc.stdout + proc.stderr).splitlines()
            if line.startswith("CONFLICT")
        )
        if conflicted:
            result = MergeResult(merged=False, fast_forward=False, conflicted=conflicted)
            self._emit(
                EventName.TOOL_FAILED,
                {"tool": "git.merge", "branch": branch, "conflicts": len(conflicted)},
                ok=False,
            )
            raise MergeConflictError(
                f"merge conflicted ({len(conflicted)} files): {list(conflicted)}"
            )
        raise GitEngineError(f"git merge failed: {(proc.stderr or proc.stdout).strip()}")

    # ----------------------------------------------------------------- tag

    def tags(self) -> tuple[TagRecord, ...]:
        """``tag`` (read) — every tag with its commit."""
        self._require_repo()
        self._emit(EventName.TOOL_CALLED, {"tool": "git.tag"})
        out = self._run(
            "for-each-ref", "--format=%(refname:short)|%(objectname)|%(objecttype)", "refs/tags/"
        )
        records: list[TagRecord] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            name, sha, objtype = line.split("|")
            annotated = objtype == "tag"
            message: str | None = None
            if annotated:
                raw = self._run("tag", "-l", "--format=%(contents)", name).strip()
                message = raw or None
            records.append(TagRecord(name=name, commit=sha, annotated=annotated, message=message))
        self._emit(EventName.TOOL_COMPLETED, {"tool": "git.tag", "count": len(records)})
        return tuple(records)

    def tag(self, name: str, *, message: str | None = None, commit: str | None = None) -> TagRecord:
        """``tag`` (write) — annotated when a message is given."""
        self._require_repo()
        if not name or not re.fullmatch(r"[A-Za-z0-9._/\-]+", name):
            raise GitEngineError(f"invalid tag name: {name!r}")
        self._emit(EventName.TOOL_CALLED, {"tool": "git.tag.create", "tag": name})
        args = ["tag"]
        if message:
            # an annotated tag carries a committer — identity must resolve
            self._ensure_identity()
            args += ["-a", name, "-m", message]
        else:
            args.append(name)
        if commit:
            args.append(commit)
        self._run(*args)
        sha = self._run("rev-list", "-1", f"refs/tags/{name}").strip()
        record = TagRecord(name=name, commit=sha, annotated=bool(message), message=message)
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "git.tag.create", "tag": name, "sha": self._short(sha)},
        )
        return record

    def delete_tag(self, name: str) -> str:
        self._require_repo()
        self._run("tag", "-d", name)
        self._emit(EventName.TOOL_COMPLETED, {"tool": "git.tag.delete", "tag": name})
        return name

    # ------------------------------------------------------------ rollback

    def rollback(
        self, ref: str, *, hard: bool = False, safety_branch: str | None = None
    ) -> RollbackResult:
        """``rollback`` — move HEAD to ``ref``; dirty work is preserved by default.

        ``hard=True`` wipes tracked changes — so the engine first saves a
        safety branch (``safety_branch`` or an auto name) unless the caller
        explicitly passes ``safety_branch=""``.
        """
        self._require_repo()
        self._emit(EventName.TOOL_CALLED, {"tool": "git.rollback", "ref": ref, "hard": hard})
        from_sha = self.head()
        if not from_sha:
            raise GitEngineError("cannot rollback an unborn HEAD")
        saved: str | None = None
        if hard and safety_branch != "":
            # A hard reset destroys commits after ``ref`` — so the engine
            # always pins them to a safety branch first (the work tree's
            # dirty state alone would not survive as a branch).  Pass
            # ``safety_branch=""`` only when the caller truly wants loss.
            name = safety_branch or f"pre-rollback-{self._short(from_sha)}"
            self._run("branch", name, from_sha)
            saved = name
        self._run("reset", "--hard" if hard else "--mixed", ref)
        to_sha = self.head()
        result = RollbackResult(from_sha=from_sha, to_sha=to_sha, safety_branch=saved, hard=hard)
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "git.rollback", "from": self._short(from_sha),
             "to": self._short(to_sha), "hard": hard},
        )
        return result

    # --------------------------------------------------------------- clone

    @classmethod
    def clone(
        cls,
        url: str,
        dest: Path | str,
        *,
        depth: int | None = None,
        branch: str | None = None,
        bus: Any = None,
        extra_config: tuple[tuple[str, str], ...] = (),
        timeout: int = 300,
    ) -> GitEngine:
        """Clone a real repository into ``dest`` and return its engine.

        Network credentials never ride on this surface — pass repo-level
        ``extra_config`` only with trusted values; the GitHub engine keeps
        tokens out of argv and payloads (Spec §124).
        """
        if shutil.which("git") is None:
            raise GitBinaryMissingError("the git executable was not found on PATH")
        target = Path(dest)
        if target.exists() and any(target.iterdir()):
            raise GitEngineError(f"destination must be empty or absent: {target}")
        if bus is not None:
            bus.publish(
                EventName.TOOL_CALLED, payload={"tool": "git.clone", "url": url}, source="nexus.git"
            )
        argv = ["git", "clone", "--quiet"]
        if depth:
            argv += ["--depth", str(depth)]
        if branch:
            argv += ["--branch", branch]
        for key, value in extra_config:
            argv += ["-c", f"{key}={value}"]
        argv += [url, str(target)]
        try:
            proc = subprocess.run(
                argv,
                env=_ENV,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitEngineError(f"git clone timed out after {timeout}s") from exc
        if proc.returncode != 0:
            raise GitEngineError(f"git clone failed: {(proc.stderr or proc.stdout).strip()}")
        engine = cls(target, bus=bus)
        if bus is not None:
            bus.publish(
                EventName.TOOL_COMPLETED,
                payload={"tool": "git.clone", "url": url, "path": str(target)},
                source="nexus.git",
            )
        return engine

    # ---------------------------------------------------------------- misc

    def log(self, *, limit: int = 10, ref: str = "HEAD") -> tuple[CommitResult, ...]:
        """Recent commits — read-only convenience built on the same surface."""
        self._require_repo()
        out = self._run(
            "log", f"-{max(1, limit)}", "--format=%H%x00%s%x00", ref
        )
        commits: list[CommitResult] = []
        for chunk in out.split("\x00\n"):
            if not chunk.strip():
                continue
            sha, message = chunk.split("\x00")
            commits.append(CommitResult(sha=sha, short_sha=self._short(sha), message=message))
        return tuple(commits)

    def is_clean(self) -> bool:
        return self.status().clean

    # ------------------------------------------------------- network (§198)

    def pull(self, *, remote: str = "origin", branch: str | None = None) -> str:
        """``pull`` (Spec §198) — fast-forward only; divergence is an error."""
        self._require_repo()
        args = ["pull", "--ff-only", remote] + ([branch] if branch else [])
        self._run(*args)
        sha = self.head()
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "git.pull", "remote": remote, "sha": self._short(sha)},
        )
        return sha

    def push(
        self, *, remote: str = "origin", branch: str | None = None, set_upstream: bool = True
    ) -> str:
        """``push`` (Spec §198) — publish commits; the remote is the judge."""
        self._require_repo()
        target = branch or self.current_branch()
        args = ["push"]
        if set_upstream:
            args += ["-u", remote, target]
        else:
            args += [remote, target]
        self._run(*args)
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "git.push", "remote": remote, "branch": target}
        )
        return target
