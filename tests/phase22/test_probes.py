"""§22.4 — the six surface probes: honest, injectable, platform-aware."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.recovery import (
    BROWSER_MARKERS,
    CompositeProbe,
    FilesProbe,
    GitProbe,
    ProcessProbe,
    TaskStateProbe,
    WindowProbe,
    browser_markers,
)


def _runner_of(lines: list[str]):
    return lambda argv: "\n".join(lines) + "\n"


def test_files_probe_hashes_the_tree(repo: Path) -> None:
    files = FilesProbe(repo).probe()
    assert set(files) == {"README.md", "src/app.py"}
    import hashlib

    want = hashlib.sha256((repo / "src" / "app.py").read_bytes()).hexdigest()
    assert files["src/app.py"] == want


def test_files_probe_detects_a_change(repo: Path) -> None:
    before = FilesProbe(repo).probe()
    (repo / "src" / "app.py").write_text("print('edited')\n", encoding="utf-8")
    after = FilesProbe(repo).probe()
    assert before["src/app.py"] != after["src/app.py"]


def test_git_probe_on_a_real_repo(repo: Path) -> None:
    if shutil.which("git") is None:  # pragma: no cover
        pytest.skip("git binary unavailable on this host")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@n.dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "n"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c1"], check=True)
    head, branch, dirty, _notes = GitProbe(repo).probe()
    assert head is not None and len(head) == 40
    assert branch in {"main", "master"}
    assert dirty is False
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    _, _, dirty2, _ = GitProbe(repo).probe()
    assert dirty2 is True


def test_git_probe_honest_on_a_non_repo(tmp_path: Path) -> None:
    head, branch, dirty, notes = GitProbe(tmp_path).probe()
    assert head is None and branch is None
    assert any("not a git repository" in n for n in notes)


def test_process_probe_windows_csv() -> None:
    raw = '"System",4\n"python.exe",12345\n"explorer.exe",999\n'
    names = ProcessProbe._parse_windows_csv(raw)
    assert names == ("explorer.exe", "python.exe", "system")


def test_process_probe_posix_ps() -> None:
    names = ProcessProbe._parse_ps("systemd\npython\n/usr/bin/git\n")
    assert "git" in names and "python" in names
    assert ProcessProbe._parse_ps("") == ()


def test_process_probe_honest_on_failure() -> None:
    def boom(argv):  # noqa: ANN001
        raise OSError("no such command")

    assert ProcessProbe(runner=boom).probe() == ()


def test_window_probe_injected() -> None:
    probe = WindowProbe(
        runner=_runner_of(["0x02 0 host editor — NVIM", "0x03 0 host browser — Firefox"]),
        argv=["fake-wmctrl", "-l"],
        title_from="wmctrl",
    )
    titles = probe.probe()
    assert titles == ("browser — Firefox", "editor — NVIM")


def test_window_probe_line_mode_and_honest_absence() -> None:
    probe = WindowProbe(
        runner=_runner_of(["Build output", "Editor — app.py"]),
        argv=["fake-powershell"],
        title_from="line",
    )
    assert probe.probe() == ("Build output", "Editor — app.py")
    # the real probe (real command, real decoder) never crashes and
    # never returns None — a tuple, even on a loud desktop
    assert isinstance(WindowProbe().probe(), tuple)


def test_browser_markers() -> None:
    procs = ("chrome.exe", "msedgewebview2.exe", "python", "notepad.exe")
    found = browser_markers(procs)  # type: ignore[arg-type]
    assert set(found) == {"chrome", "msedge"}
    assert browser_markers(()) == ()
    assert all(m in BROWSER_MARKERS for m in found)


def test_task_state_probe(tmp_path: Path) -> None:
    path = tmp_path / "task_state.json"
    assert TaskStateProbe(path).probe() == {}  # missing — honest
    path.write_text(json.dumps({"step": 3}), encoding="utf-8")
    assert TaskStateProbe(path).probe() == {"step": 3}
    path.write_text("{corrupt", encoding="utf-8")
    assert TaskStateProbe(path).probe() == {}  # unreadable ≠ matching


def test_composite_probe_six_surfaces(repo: Path, tmp_path: Path) -> None:
    state_path = tmp_path / "task_state.json"
    state_path.write_text(json.dumps({"task": "T-9", "state": "RUNNING"}), encoding="utf-8")
    probe = CompositeProbe(
        repo,
        state_path,
        processes=ProcessProbe(runner=_runner_of(["python", "chrome"])),
        windows=WindowProbe(
            runner=_runner_of(["Editor — app.py"]),
            argv=["fake-powershell"],
            title_from="line",
        ),
    )
    facts = probe.probe()
    assert set(facts.files) == {"README.md", "src/app.py"}
    assert facts.processes == ("chrome", "python")
    assert facts.browser == ("chrome",)
    assert facts.windows == ("Editor — app.py",)
    assert facts.task_state == {"task": "T-9", "state": "RUNNING"}
    assert facts.probed_at_utc
