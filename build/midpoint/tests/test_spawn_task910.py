# -*- coding: utf-8 -*-
"""GATE #9/#10 spawn test — launches the detached installer worker."""
import os
import subprocess
import sys

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.abspath(os.path.join(HERE, "..", "worker_task910.py"))
LOG = os.path.abspath(os.path.join(HERE, "..", "worker_task910.spawn.log"))


def _spawn(flags: int):
    with open(LOG, "a", encoding="utf-8") as fh:
        return subprocess.Popen(
            [sys.executable, "-u", WORKER],
            stdout=fh, stderr=subprocess.STDOUT,
            cwd=os.path.dirname(WORKER),
            creationflags=flags, close_fds=True)


def test_spawn_gate910_worker():
    assert os.path.isfile(WORKER), f"worker missing: {WORKER}"
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        proc = _spawn(flags | CREATE_BREAKAWAY_FROM_JOB)
    except OSError:
        proc = _spawn(flags)
    assert proc.pid > 0
    print("spawned gate910 worker pid:", proc.pid)
