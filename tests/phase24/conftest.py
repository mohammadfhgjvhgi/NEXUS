"""Phase-24 test fixtures — repo root on sys.path (house pattern)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def registry(tmp_path: Path):
    """A §6.4 AgentRegistry over a temp data dir."""
    from nexus.agents import AgentRegistry

    return AgentRegistry(tmp_path / "data")


@pytest.fixture()
def ownership():
    """A fresh §6.6 OwnershipManager."""
    from nexus.agents import OwnershipManager

    return OwnershipManager()


@pytest.fixture()
def team(registry, ownership):
    """The §24.2 thirteen, built on the temp registry."""
    from nexus.orchestration import SpecialistTeam

    return SpecialistTeam.build(registry, "fixture task")
