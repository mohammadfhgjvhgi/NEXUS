# -*- coding: utf-8 -*-
"""Spawn trigger for _gh31_worker.py — one pytest call, detached worker.

The push can take minutes (tunnel-independent); the worker runs DETACHED
and writes progressive results to _gh31_result.json / _gh31_state.json.
Guard: skip if a fresh state heartbeat exists (<120s old).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]      # M:\NEXUS
WORKER = HERE / "_gh31_worker.py"
REC = HERE / "_gh31_spawn_record.json"
STATE = HERE / "_gh31_state.json"


def _state_fresh() -> bool:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
        age = time.time() - time.mktime(time.strptime(
            st["utc"], "%Y-%m-%dT%H:%M:%SZ"))
        return age < 120
    except BaseException:
        return False


def test_gh31_upload_trigger() -> None:
    if _state_fresh():
        return
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log = HERE / "_gh31_worker.log"
    fh = open(log, "a", encoding="utf-8")
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_GROUP
    proc = subprocess.Popen(
        [sys.executable, str(WORKER)], stdout=fh, stderr=fh,
        stdin=subprocess.DEVNULL, creationflags=flags, cwd=str(HERE))
    fh.close()
    REC.write_text(json.dumps(
        {"triggered_utc": stamp, "pid": proc.pid},
        ensure_ascii=False, indent=1), encoding="utf-8")
    assert proc.pid > 0
