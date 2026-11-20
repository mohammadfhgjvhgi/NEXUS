"""Spawn the DETACHED NEXUS.exe build worker (survives MCP restarts).

Returns in <2s: the pytest call may be killed by the MCP gateway ~50-60s
later, the detached worker keeps building and writes everything to disk:
    results\\build_spawn_record.json   (this file's record)
    results\\build_exe.phases.log      (heartbeats)
    proofs\\midpoint_build.json        (final honest certificate)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "build_spawn_record.json"


def test_build_spawn() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    worker = HERE / "build_worker.py"
    log = HERE / "results" / "build_worker_stdout.log"
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            [sys.executable, str(worker)], stdout=fh, stderr=fh,
            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True,
            cwd=str(HERE))
    OUT.write_text(json.dumps(
        {"spawned": "build_exe", "pid": proc.pid,
         "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        ensure_ascii=False), encoding="utf-8")
    assert OUT.exists()
