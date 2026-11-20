"""diagnostic: is the mover orphan alive? + robocopy instances + src count."""
from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path

OUT = Path(r"M:\NEXUS\tools\c_relief\results\diag.json")
SRC = r"C:\Users\MohandsMohammad\AppData\Local\Arduino15"

def tree_count(root: str) -> int:
    count = 0
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            count += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return count

def test_diag() -> None:
    res = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for label, flt in (("mover_pid_13536", 'PID eq 13536'), ("robocopy", "IMAGENAME eq robocopy.exe")):
        p = subprocess.run(["tasklist", "/FI", flt, "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=30)
        out = (p.stdout or "").strip()
        res[label] = out if ("Info:" in out or not out) else out[:400]
    p2 = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                        capture_output=True, text=True, timeout=30)
    res["python_procs"] = (p2.stdout or "").strip()[:800]
    try:
        res["src_files"] = tree_count(SRC)
    except Exception as exc:  # noqa: BLE001
        res["src_files"] = f"err:{exc}"[:100]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
