"""Phase-22 test fixtures — repo root on sys.path (house pattern)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A planted workspace tree — the recovery fixture world.

    Written as bytes on purpose: text-mode writes translate \\n to
    \\r\\n on Windows and byte-exact assertions would split by
    platform (the environment is the judge).
    """
    work = tmp_path / "repo"
    work.mkdir()
    (work / "src").mkdir()
    (work / "src" / "app.py").write_bytes(b"print('nexus-22')\n")
    (work / "README.md").write_bytes(b"checkpoint fixture\n")
    return work
