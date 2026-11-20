"""Spawn the Phase-8 harness detached, log to file (the bridge
caps synchronous shell time ~30s; this is standard async job + poll)."""
import subprocess
import sys

log = open(r"M:\NEXUS\tests\phase08\harness_out.txt", "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, "-u", r"M:\NEXUS\tests\phase08\verify_exit_criteria.py"],
    stdout=log,
    stderr=subprocess.STDOUT,
)
print("harness pid:", proc.pid)
