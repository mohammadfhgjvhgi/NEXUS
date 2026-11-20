"""arduino15 finish: rmdir empty husk + mklink /J + verify."""
from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path

OUT = Path(r"M:\NEXUS\tools\c_relief\results\arduino15_finish.json")
SRC = r"C:\Users\MohandsMohammad\AppData\Local\Arduino15"
DST = r"M:\C-RELIEF\mohands\AppData\Arduino15"

def test_finish() -> None:
    res = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    # safety: only remove the husk if it is a real, EMPTY dir (no data loss possible)
    if os.path.exists(SRC) and not os.path.islink(SRC):
        leftovers = []
        try:
            leftovers = os.listdir(SRC)
        except OSError as e:
            res["listdir_err"] = str(e)[:120]
        res["leftover_entries"] = leftovers[:10]
        if not leftovers:
            try:
                os.rmdir(SRC)
                res["husk_removed"] = True
            except OSError as e:
                res["husk_removed"] = False
                res["rmdir_err"] = str(e)[:150]
        else:
            res["husk_removed"] = False
            res["abort"] = "NOT EMPTY — no touch"
    if not os.path.exists(SRC):
        mk = subprocess.run(["cmd", "/c", "mklink", "/J", SRC, DST],
                            capture_output=True, text=True, timeout=30)
        res["mklink_rc"] = mk.returncode
        res["mklink_out"] = ((mk.stdout or "") + (mk.stderr or ""))[:200]
    res["junction_ok"] = os.path.exists(SRC) and os.path.realpath(SRC).lower() == DST.lower()
    # sanity through the junction: package index visible?
    try:
        res["spot_check_entries"] = len(os.listdir(SRC))
    except OSError as e:
        res["spot_check_entries"] = f"err:{e}"[:100]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
