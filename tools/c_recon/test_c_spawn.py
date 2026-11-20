"""Spawn a DETACHED c-relief worker (survives MCP restarts). Returns instantly."""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

BASE = Path(r"M:\NEXUS\tools\c_relief")
TARGET = BASE / "target.json"
OUT = BASE / "results" / "spawn_record.json"

def test_c_spawn() -> None:
    spec = json.loads(TARGET.read_text(encoding="utf-8"))
    worker = str(BASE / "worker.py")
    log = str(BASE / "results" / "worker_stdout.log")
    if spec.get("spawn") == "recon":
        args = [sys.executable, worker, "recon"]
    else:
        args = [sys.executable, worker, spec["spawn"], spec["name"], spec["src"], spec["dst"]]
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(log, "ab") as fh:
        proc = subprocess.Popen(args, stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                                creationflags=flags, close_fds=True)
    OUT.write_text(json.dumps({"spawned": spec.get("spawn"), "pid": proc.pid,
                               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                              ensure_ascii=False), encoding="utf-8")
    assert OUT.exists()
