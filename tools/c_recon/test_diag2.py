"""diag2: is whale orphan pid 10152 alive? + python/robocopy procs."""
from __future__ import annotations
import json, subprocess, time
from pathlib import Path

OUT = Path(r"M:\NEXUS\tools\c_relief\results\diag2.json")

def test_diag2() -> None:
    res = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for label, flt in (("whale_pid_10152", "PID eq 10152"),
                       ("robocopy", "IMAGENAME eq robocopy.exe")):
        p = subprocess.run(["tasklist", "/FI", flt, "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=30)
        out = (p.stdout or "").strip()
        res[label] = "NONE" if ("Info:" in out or not out) else out[:300]
    p2 = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                        capture_output=True, text=True, timeout=30)
    res["python_procs"] = (p2.stdout or "").strip()[:900]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
