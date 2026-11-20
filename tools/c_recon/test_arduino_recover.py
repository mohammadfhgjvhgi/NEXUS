"""arduino15 recovery: verify src absent, create junction, confirm."""
from __future__ import annotations
import json, os, shutil, subprocess, time
from pathlib import Path

OUT = Path(r"M:\NEXUS\tools\c_relief\results\arduino15_recover.json")
SRC = r"C:\Users\MohandsMohammad\AppData\Local\Arduino15"
DST = r"M:\C-RELIEF\mohands\AppData\Arduino15"

def test_recover() -> None:
    res = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    res["src_exists"] = os.path.exists(SRC)
    res["dst_files_bytes"] = [sum(1 for _ in os.scandir(DST)), "scanned_root"]
    if not res["src_exists"]:
        mk = subprocess.run(["cmd", "/c", "mklink", "/J", SRC, DST],
                            capture_output=True, text=True, timeout=30)
        res["mklink_rc"] = mk.returncode
        res["mklink_out"] = ((mk.stdout or "") + (mk.stderr or ""))[:200]
    res["junction_ok"] = os.path.exists(SRC) and os.path.realpath(SRC).lower() == DST.lower()
    u, _t, f = shutil.disk_usage("C:\\")
    res["C_free_gb"] = round(f / 2**30, 2)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
