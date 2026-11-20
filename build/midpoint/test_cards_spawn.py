"""Spawn the DETACHED MIDPOINT-10 worker (cards + project card + rebuild)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "cards_spawn_record.json"


def test_cards_spawn() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    worker = HERE / "worker_cards.py"
    log = HERE / "results" / "cards_worker_stdout.log"
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            [sys.executable, str(worker)], stdout=fh, stderr=fh,
            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True,
            cwd=str(HERE))
    OUT.write_text(json.dumps(
        {"spawned": "midpoint10_cards", "pid": proc.pid,
         "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        ensure_ascii=False), encoding="utf-8")
    assert OUT.exists()
