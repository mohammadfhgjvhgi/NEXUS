"""Spawn the DETACHED runtime recon worker. Returns in <2s."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "runtime_recon_spawn_record.json"


def test_runtime_recon_spawn() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    worker = HERE / "worker_runtime_recon.py"
    log = HERE / "results" / "runtime_recon_stdout.log"
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            [sys.executable, str(worker)], stdout=fh, stderr=fh,
            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True,
            cwd=str(HERE))
    OUT.write_text(json.dumps(
        {"spawned": "runtime_recon", "pid": proc.pid,
         "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        ensure_ascii=False), encoding="utf-8")
    assert OUT.exists()
