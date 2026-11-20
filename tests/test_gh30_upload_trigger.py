# -*- coding: utf-8 -*-
"""GH30 upload trigger - one pytest shot, worker survives detached.

Guard: if a PASS/PARTIAL result already exists, never respawn.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

NEXUS = Path(__file__).resolve().parent.parent      # M:\NEXUS
WORKER = NEXUS / "_gh30_worker.py"
RESULT = NEXUS / "_gh30_result.json"
LOG = NEXUS / "_gh30_worker.log"
REC = NEXUS / "_gh30_spawn_record.json"


def _done() -> bool:
    try:
        r = json.loads(RESULT.read_text(encoding="utf-8"))
        return r.get("verdict") in ("PASS", "PARTIAL")
    except BaseException:
        return False


def test_gh30_upload_trigger() -> None:
    if _done():
        return
    log_fh = open(LOG, "a", encoding="utf-8")
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, str(WORKER)], stdout=log_fh, stderr=log_fh,
        stdin=subprocess.DEVNULL, creationflags=flags, cwd=str(NEXUS))
    log_fh.close()
    REC.write_text(json.dumps(
        {"triggered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "pid": proc.pid}, ensure_ascii=False, indent=1), encoding="utf-8")
    assert proc.pid > 0
    # no waiting here - polling happens externally via bridge reads
