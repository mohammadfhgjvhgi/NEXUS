"""Run the Phase-9 exit-criteria harness ON the real machine, detached.

The bridge caps synchronous shell time (~30s) and may host commands in
a job object that reaps children when the session ends — so the
harness is spawned fully detached (breakaway) writing to a log, and
the caller polls ``device_harness_out.txt``:

    python tests\\phase09\\run_device_harness.py
    # … later …
    type tests\\phase09\\device_harness_out.txt

Run:  python tests\\phase09\\run_device_harness.py   (from M:\\NEXUS)
"""

import subprocess
import sys

#: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
_DETACHED = 0x00000008 | 0x00000200 | 0x01000000

LOG = r"M:\NEXUS\tests\phase09\device_harness_out.txt"

log = open(LOG, "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-u", r"M:\NEXUS\tests\phase09\verify_exit_criteria.py"],
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=_DETACHED,
    close_fds=True,
)
print("harness pid:", proc.pid)
print("log:", LOG)
