# -*- coding: utf-8 -*-
"""Spawn trigger for skill_worker.py (PHASE 31 — Skill System).

One pytest trigger, then read-only polling. Guard: if the worker already
reports a fresh+running heartbeat, do NOT respawn.
"""
from __future__ import annotations

import calendar
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # M:\NEXUS\skills
WORKER = HERE / "skill_worker.py"
REC = HERE / "worker_phase31_spawn_record.json"
HB = HERE / ".hb.json"


def _hb_fresh() -> bool:
    try:
        hb = json.loads(HB.read_text(encoding="utf-8"))
        age = time.time() - calendar.timegm(
            time.strptime(hb["utc"], "%Y-%m-%dT%H:%M:%SZ"))
        return age < 120 and hb.get("running") is True
    except BaseException:
        return False


def test_phase31_spawn() -> None:
    if _hb_fresh():
        return
    hb_before = None
    try:
        hb_before = json.loads(HB.read_text(encoding="utf-8"))
    except BaseException:
        hb_before = None
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log = HERE / "worker_phase31.log"
    log.parent.mkdir(exist_ok=True)
    fh = open(log, "a", encoding="utf-8")
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_GROUP
    proc = subprocess.Popen(
        [sys.executable, str(WORKER)], stdout=fh, stderr=fh,
        stdin=subprocess.DEVNULL, creationflags=flags, cwd=str(HERE))
    fh.close()
    REC.write_text(json.dumps(
        {"triggered_utc": stamp, "pid": proc.pid, "hb_before": hb_before},
        ensure_ascii=False, indent=1), encoding="utf-8")
    assert proc.pid > 0
