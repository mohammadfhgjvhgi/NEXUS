"""Spawn the Phase-8 harness fully detached (breakaway from any
job object so it survives the shell_exec session) and log to file."""
import subprocess
import sys

DETACHED = 0x00000008 | 0x00000200 | 0x01000000  # DETACHED | NEW_PROCESS_GROUP | BREAKAWAY_FROM_JOB
log = open(r"M:\NEXUS\tests\phase08\final_run2.txt", "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-u", r"M:\NEXUS\tests\phase08\verify_exit_criteria.py"],
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=DETACHED,
    close_fds=True,
)
print("pid:", proc.pid)
