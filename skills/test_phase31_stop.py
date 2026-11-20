# -*- coding: utf-8 -*-
"""One-shot STOP signal for the PHASE 31 resident worker.

Writes skills\\STOP — the resident worker checks it every 30s scan and
exits cleanly (heartbeat running=false). Read-only polling afterwards;
respawn happens via the regular spawn trigger once the guard clears.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent          # M:\NEXUS\skills


def test_phase31_stop() -> None:
    (HERE / "STOP").write_text("stop-phase31", encoding="utf-8")
    assert (HERE / "STOP").is_file()
