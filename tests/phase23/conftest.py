"""Phase-23 test fixtures — repo root on sys.path (house pattern)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeClock:
    """A monotonic clock the tests drive by hand — time is a variable,
    never a wait."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()
