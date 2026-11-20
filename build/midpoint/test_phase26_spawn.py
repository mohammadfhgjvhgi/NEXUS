# -*- coding: utf-8 -*-
"""Spawn trigger for worker_phase26.py — one pytest trigger, then read-only.

The worker runs DETACHED so it survives tunnel disconnection; we poll its
heartbeat/result files afterwards (never re-trigger while it may run).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # ...\build\midpoint
WORKER = HERE / "worker_phase26.py"
REC = HERE / "results" / "phase26_spawn_record.json"
HB = HERE / "results" / "worker_phase26.hb.json"


def test_spawn_phase26() -> None:
    hb_before = None
    try:
        hb_before = json.loads(HB.read_text(encoding="utf-8"))
    except BaseException:
        hb_before = None
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log = HERE / "results" / "worker_phase26.log"
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
    # do NOT wait here — the tunnel session must stay cheap; polling is external
