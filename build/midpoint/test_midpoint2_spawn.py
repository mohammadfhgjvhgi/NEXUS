"""Spawn the DETACHED midpoint v2 worker (rebuild exe + first real chat).

Returns in <2s. Evidence lands on disk:
    results\\build_exe.phases.log / chat_exe.phases.log (heartbeats)
    proofs\\midpoint_build.json / midpoint_chat.json     (honest certs)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "midpoint2_spawn_record.json"


def test_midpoint2_spawn() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    worker = HERE / "worker_midpoint2.py"
    log = HERE / "results" / "midpoint2_worker_stdout.log"
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            [sys.executable, str(worker)], stdout=fh, stderr=fh,
            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True,
            cwd=str(HERE))
    OUT.write_text(json.dumps(
        {"spawned": "midpoint_v2_build_plus_chat", "pid": proc.pid,
         "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        ensure_ascii=False), encoding="utf-8")
    assert OUT.exists()
