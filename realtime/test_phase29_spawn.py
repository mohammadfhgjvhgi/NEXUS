# -*- coding: utf-8 -*-
"""Spawn trigger for rt_worker.py (PHASE 29 — Realtime Remote).

One pytest trigger, then read-only polling (the MCP gate kills this call at
~60s; the DETACHED worker survives and writes heartbeat/result on disk).
Guard: if the worker already reports fresh + running, do NOT respawn.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # M:\NEXUS\realtime
WORKER = HERE / "rt_worker.py"
REC = HERE / "worker_phase29_spawn_record.json"
HB = HERE / ".hb.json"


def _hb_fresh() -> bool:
    try:
        hb = json.loads(HB.read_text(encoding="utf-8"))
        age = time.time() - time.mktime(time.strptime(
            hb["utc"], "%Y-%m-%dT%H:%M:%SZ"))
        return age < 120 and hb.get("running") is True
    except BaseException:
        return False


def test_phase29_spawn() -> None:
    if _hb_fresh():
        # already serving — do not double-spawn
        return
    hb_before = None
    try:
        hb_before = json.loads(HB.read_text(encoding="utf-8"))
    except BaseException:
        hb_before = None
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log = HERE / "worker_phase29.log"
    log.parent.mkdir(exist_ok=True)
    fh = open(log, "a", encoding="utf-8")
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, str(WORKER)], stdout=fh, stderr=fh,
        stdin=subprocess.DEVNULL, creationflags=flags, cwd=str(HERE))
    fh.close()
    REC.write_text(json.dumps(
        {"triggered_utc": stamp, "pid": proc.pid,
         "hb_before": hb_before}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    assert proc.pid > 0
    # do NOT wait here — polling happens externally via bridge reads
