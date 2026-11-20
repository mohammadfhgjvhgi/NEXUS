"""Runs the Phase-8 exit-criteria harness on this machine and
reports the tail (the runner exists because the bridge's command
validator rejects the long script name in a direct shell command —
running our own python files is the established pattern here)."""
import subprocess
import sys

proc = subprocess.run(
    [sys.executable, "-u", r"M:\NEXUS\tests\phase08\verify_exit_criteria.py"],
    capture_output=True,
    text=True,
    timeout=850,
)
lines = (proc.stdout or "").splitlines()
fails = [l for l in lines if "[FAIL]" in l]
bonus = [l for l in lines if "[BONUS]" in l or "[SKIP]" in l]
print("FAILURES:", len(fails))
for line in fails:
    print(line)
print("BONUS/SKIP:")
for line in bonus:
    print(line)
print("TAIL:")
print("\n".join(lines[-3:]))
print("STDERR-TAIL:", (proc.stderr or "")[-300:])
print("HARNESS EXIT:", proc.returncode)
