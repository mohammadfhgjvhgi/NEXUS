"""Phase-25 test fixtures — repo root on sys.path (house pattern)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeWall:
    """A wall clock the tests drive by hand — epoch time is a variable,
    never a wait (§25.7 deadlines are epoch-based on purpose)."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


@pytest.fixture()
def wall() -> FakeWall:
    return FakeWall()


@pytest.fixture()
def store(tmp_path: Path):
    from nexus.horizon import GoalStore

    return GoalStore(tmp_path / "goals")


@pytest.fixture()
def runner(store, wall):
    from nexus.horizon import HorizonRunner

    return HorizonRunner(store, wall_clock=wall)
