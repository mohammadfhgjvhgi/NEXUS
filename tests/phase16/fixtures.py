"""Shared fixtures for the Phase 16 suite — real repos, no fakes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "NEXUS Phase 16",
    "GIT_AUTHOR_EMAIL": "nexus@phase16.local",
    "GIT_COMMITTER_NAME": "NEXUS Phase 16",
    "GIT_COMMITTER_EMAIL": "nexus@phase16.local",
    "GIT_TERMINAL_PROMPT": "0",
}


def git(repo: Path, *args: str) -> str:
    """Run one git command in ``repo`` (test-side, not the engine)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=_ENV,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def init_repo(path: Path, *, default_branch: str = "main") -> Path:
    """A real repo with one real commit — the smallest honest workspace."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", default_branch)
    (path / "README.md").write_text("# temp repo\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-m", "init: seed repository")
    return path


def make_bare_origin(seed: Path, dest: Path) -> Path:
    """A real bare remote — push/pull tests run over it, no network."""
    git(dest.parent, "clone", "--bare", str(seed), str(dest))
    return dest


def add_remote(repo: Path, name: str, url: str) -> None:
    git(repo, "remote", "add", name, url)
