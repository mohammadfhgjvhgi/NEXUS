# -*- coding: utf-8 -*-
"""One-shot STOP signal for the PHASE 30 resident worker.

Writes plugins\\STOP — the resident worker checks it every 30s scan and
exits cleanly (heartbeat running=false). Read-only polling afterwards;
respawn happens via the regular spawn trigger once the guard clears.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent          # M:\NEXUS\plugins


def test_phase30_stop() -> None:
    (HERE / "STOP").write_text("stop-phase30", encoding="utf-8")
    assert (HERE / "STOP").is_file()
