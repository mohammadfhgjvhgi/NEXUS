"""Environment probes — the §22.4 six surfaces, measured live.

The §22.4 law, verbatim: «لا يعتمد على الذاكرة» — a resume decision
never trusts memory; it probes:

    Files · Git · Processes · Windows · Browser · Task state

Every probe here measures the *actual* machine and is honest about
what it could not measure (notes + neutral facts, never invented
ones).  Each probe accepts an injectable command runner so tests and
the device proof can drive it deterministically.

Platform notes:

* Processes  — Windows: ``tasklist /FO CSV /NH`` · POSIX: ``ps -eo comm=``
* Windows    — PowerShell ``Get-Process`` main-window titles ·
               POSIX: ``wmctrl -l`` when present, else an honest empty
* Browser    — browser markers found among the process names
* Git        — the git binary when present, stdlib ``.git`` parsing
               as fallback, ``git_head=None`` when not a repository

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from .contracts import EnvironmentFacts, VerificationSurface, utc_now_iso

Runner = Callable[[list[str]], str]

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache"}
SKIP_SUFFIXES = (".pyc", ".pyo")

#: browser markers matched against lowercased process names
BROWSER_MARKERS: tuple[str, ...] = (
    "chrome",
    "msedge",
    "firefox",
    "brave",
    "opera",
    "vivaldi",
    "chromium",
)


def _default_runner(argv: list[str]) -> str:
    """The house runner — decode-proof on real machines.

    Real console tools (PowerShell on an Arabic-locale Windows box,
    for one) emit bytes in whatever codepage they like; a strict
    utf-8 decode kills the reader thread and leaves ``stdout`` as
    ``None`` (device discovery, phase 22).  ``errors="replace"`` keeps
    the probe honest — mangled characters, never a crash, and the
    same decoder on capture and probe keeps comparisons fair.
    """
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return completed.stdout or ""


def _windows_runner(argv: list[str]) -> str:  # pragma: no cover - platform
    return _default_runner(argv)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_files(root: Path, max_file_bytes: int = 2_000_000) -> dict[str, str]:
    """Rel-path → sha256 over the tree — shared by capture and probe so
    both sides of §22.4 comparison speak one dialect (posix rel paths)."""
    out: dict[str, str] = {}
    base = Path(root)
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(base).parts
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel_parts[:-1]):
            continue
        if path.name.startswith(".") or path.suffix in SKIP_SUFFIXES:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
            out[path.relative_to(base).as_posix()] = sha256_file(path)
        except OSError:
            continue  # vanished mid-walk — honestly absent
    return out


# ---------------------------------------------------------------- probes


class FilesProbe:
    """§22.4 surface 1 — the tree, hashed now."""

    def __init__(self, root: Path, max_file_bytes: int = 2_000_000) -> None:
        self._root = Path(root)
        self._max = max_file_bytes

    def probe(self) -> dict[str, str]:
        return inventory_files(self._root, self._max)


class GitProbe:
    """§22.4 surface 2 — head, branch, dirty; honest when not a repo."""

    def __init__(self, root: Path, runner: Runner | None = None) -> None:
        self._root = Path(root)
        self._runner = runner or _default_runner

    def probe(self) -> tuple[str | None, str | None, bool, tuple[str, ...]]:
        notes: list[str] = []
        head, branch, dirty = None, None, False
        try:
            raw_head = (
                self._runner(
                    ["git", "-C", str(self._root), "rev-parse", "HEAD"]
                )
                or ""
            ).strip()
        except (OSError, subprocess.SubprocessError, ValueError):
            raw_head = ""  # binary absent or unusable — stdlib fallback next
        if raw_head and not raw_head.startswith("fatal"):
            head = raw_head
            try:
                branch = self._runner(
                    ["git", "-C", str(self._root), "rev-parse", "--abbrev-ref", "HEAD"]
                ).strip()
                status = self._runner(
                    ["git", "-C", str(self._root), "status", "--porcelain"]
                )
                dirty = bool(status.strip())
            except (OSError, subprocess.SubprocessError, ValueError):
                notes.append("head read but status unavailable")
        else:
            # git unusable here — stdlib .git fallback, honestly noted
            head, branch = self._stdlib_head()
            if head is None:
                notes.append(
                    "not a git repository"
                    if not (self._root / ".git").exists()
                    else "git present but repository unreadable"
                )
            else:
                notes.append("git binary absent — stdlib .git read, dirty unknown")
        return head, branch, dirty, tuple(notes)

    def _stdlib_head(self) -> tuple[str | None, str | None]:
        git_dir = self._root / ".git"
        head_file = git_dir / "HEAD"
        if not head_file.is_file():
            return None, None
        try:
            text = head_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None, None
        if text.startswith("ref:"):
            ref = text[4:].strip()
            ref_file = git_dir / ref
            try:
                head = ref_file.read_text(encoding="utf-8").strip() or None
            except OSError:
                head = None
            return head, ref.rsplit("/", 1)[-1]
        return (text or None), None


class ProcessProbe:
    """§22.4 surface 3 — the process table, by name."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or _default_runner

    def _argv(self) -> list[str]:
        if sys.platform == "win32":  # pragma: no cover - platform
            return ["tasklist", "/FO", "CSV", "/NH"]
        return ["ps", "-eo", "comm="]

    @staticmethod
    def _parse_windows_csv(raw: str) -> tuple[str, ...]:
        """tasklist /FO CSV /NH — ``"name","pid",…`` rows."""
        import csv
        import io

        names: set[str] = set()
        for row in csv.reader(io.StringIO(raw)):
            if row and row[0].strip():
                names.add(row[0].strip().strip('"').lower())
        return tuple(sorted(names))

    @staticmethod
    def _parse_ps(raw: str) -> tuple[str, ...]:
        """``ps -eo comm=`` — one command name per line."""
        names: set[str] = set()
        for line in raw.splitlines():
            name = line.strip()
            if name:
                names.add(name.rsplit("/", 1)[-1].lower())
        return tuple(sorted(names))

    def _parse(self, raw: str) -> tuple[str, ...]:
        if sys.platform == "win32":  # pragma: no cover - platform
            return self._parse_windows_csv(raw)
        return self._parse_ps(raw)

    def probe(self) -> tuple[str, ...]:
        try:
            raw = self._runner(self._argv())
        except (OSError, subprocess.SubprocessError):
            return ()  # honest absence — never invented names
        return self._parse(raw or "")


class WindowProbe:
    """§22.4 surface 4 — visible window titles.

    ``argv``/``title_from`` are documented injection seams for tests:
    pass ``argv`` to force a command and ``title_from`` to pick the
    title extraction (``"line"`` — whole line, PowerShell dialect;
    ``"wmctrl"`` — the fourth column of ``wmctrl -l``; ``"auto"`` —
    by platform).
    """

    def __init__(
        self,
        runner: Runner | None = None,
        argv: list[str] | None = None,
        title_from: str = "auto",
    ) -> None:
        self._runner = runner or _default_runner
        self._argv_override = argv
        self._title_from = title_from

    def _argv(self) -> list[str] | None:
        if self._argv_override is not None:
            return self._argv_override
        if sys.platform == "win32":  # pragma: no cover - platform
            return [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process | Where-Object { $_.MainWindowTitle } "
                "| ForEach-Object { $_.MainWindowTitle }",
            ]
        return ["wmctrl", "-l"] if self._have_wmctrl() else None

    def _title_mode(self) -> str:
        if self._title_from != "auto":
            return self._title_from
        return "line" if sys.platform == "win32" else "wmctrl"

    @staticmethod
    def _parse_titles(raw: str, mode: str) -> tuple[str, ...]:
        titles: set[str] = set()
        for line in raw.splitlines():
            if not line.strip():
                continue
            if mode == "wmctrl":
                parts = line.split(maxsplit=3)
                if len(parts) == 4:
                    titles.add(parts[3].strip())
            else:
                titles.add(line.strip())
        return tuple(sorted(titles))

    @staticmethod
    def _have_wmctrl() -> bool:
        try:
            subprocess.run(
                ["wmctrl", "--version"], capture_output=True, timeout=10, check=False
            )
            return True
        except OSError:
            return False

    def probe(self) -> tuple[str, ...]:
        argv = self._argv()
        if argv is None:
            return ()  # honest: no enumeration means on this host
        try:
            raw = self._runner(argv)
        except (OSError, subprocess.SubprocessError):
            return ()
        return self._parse_titles(raw or "", self._title_mode())


def browser_markers(processes: tuple[str, ...]) -> tuple[str, ...]:
    """§22.4 surface 5 — browser names among the process names."""
    found: set[str] = set()
    for name in processes:
        for marker in BROWSER_MARKERS:
            if marker in name:
                found.add(marker)
    return tuple(sorted(found))


class TaskStateProbe:
    """§22.4 surface 6 — the persisted task-state document.

    A missing or unreadable file reads as ``{}`` — which cannot equal
    a non-empty checkpoint state, so corruption surfaces as drift and
    never as a silent pass.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def probe(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return {}


class CompositeProbe:
    """All six §22.4 surfaces in one :class:`EnvironmentFacts`."""

    def __init__(
        self,
        root: Path,
        task_state_path: Path,
        *,
        files: FilesProbe | None = None,
        git: GitProbe | None = None,
        processes: ProcessProbe | None = None,
        windows: WindowProbe | None = None,
        task_state: TaskStateProbe | None = None,
    ) -> None:
        self._files = files or FilesProbe(root)
        self._git = git or GitProbe(root)
        self._processes = processes or ProcessProbe()
        self._windows = windows or WindowProbe()
        self._task = task_state or TaskStateProbe(task_state_path)

    def probe(self) -> EnvironmentFacts:
        notes: list[str] = []
        files = self._files.probe()
        head, branch, dirty, git_notes = self._git.probe()
        notes.extend(git_notes)
        procs = self._processes.probe()
        windows = self._windows.probe()
        if not windows:
            notes.append("windows surface unavailable on this host")
        state = self._task.probe()
        return EnvironmentFacts(
            files=files,
            git_head=head,
            git_branch=branch,
            git_dirty=dirty,
            processes=procs,
            windows=windows,
            browser=browser_markers(procs),
            task_state=state,
            notes=tuple(notes),
            probed_at_utc=utc_now_iso(),
        )


# ------------------------------------------------- expectations capture


def capture_expectations(
    processes: tuple[str, ...],
    windows: tuple[str, ...],
    browser: tuple[str, ...],
) -> dict[str, list[str]]:
    """The environment snapshot stored inside every manifest — the
    baseline §22.4 compares the next live probe against."""
    return {
        "processes": sorted(processes),
        "windows": sorted(windows),
        "browser": sorted(browser),
    }


def surfaces_of(facts: EnvironmentFacts) -> tuple[VerificationSurface, ...]:
    """The six surfaces in §22.4 order — a convenience for reports."""
    return tuple(VerificationSurface(s) for s in ("files", "git", "processes",
                                                  "windows", "browser", "task_state"))


def facts_files_view(facts: EnvironmentFacts) -> Mapping[str, str]:
    return facts.files
