"""Spawn the C-RELIEF AUTOPILOT detached — ONE trigger, then read-only polling.

The autopilot survives MCP service crashes / tunnel deaths (DETACHED_PROCESS).
Safe to re-trigger at any time: refuses to double-spawn while a fresh run is live.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"M:\NEXUS\tools\c_relief")
RESULTS = BASE / "results"
STATUS = RESULTS / "autopilot_status.json"
PHASES_LOG = RESULTS / "autopilot.phases.log"
OUT = RESULTS / "autopilot_spawn.json"
LOG = RESULTS / "autopilot_stdout.log"
FRESH_SECONDS = 300


def test_c_autopilot_spawn() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)

    already = False
    try:
        st = json.loads(STATUS.read_text(encoding="utf-8"))
        ages = [time.time() - f.stat().st_mtime
                for f in (STATUS, PHASES_LOG) if f.exists()]
        already = (not st.get("done")) and bool(ages) and min(ages) < FRESH_SECONDS
    except Exception:  # noqa: BLE001
        already = False

    if already:
        OUT.write_text(json.dumps({"spawned": False, "reason": "already_running",
                                   "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                  ensure_ascii=False), encoding="utf-8")
        assert OUT.exists()
        return

    args = [sys.executable, str(BASE / "autopilot.py")]
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(LOG, "ab") as fh:
        proc = subprocess.Popen(args, stdout=fh, stderr=fh,
                                stdin=subprocess.DEVNULL,
                                creationflags=flags, close_fds=True)
    OUT.write_text(json.dumps({"spawned": True, "pid": proc.pid,
                               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                              ensure_ascii=False), encoding="utf-8")
    time.sleep(1.0)
    assert OUT.exists()
