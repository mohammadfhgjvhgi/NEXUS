"""C-RELIEF quick recon — drive free space + candidate src states (read-only)."""
from __future__ import annotations
import json, os, shutil, time
from pathlib import Path

OUT = Path(r"M:\NEXUS\tools\c_relief\results\quick_recon.json")
PROFILE = r"C:\Users\MohandsMohammad"
CANDS = {
    "cache": PROFILE + r"\.cache",
    "gradle": PROFILE + r"\.gradle",
    "platformio": PROFILE + r"\.platformio",
    "bun": PROFILE + r"\.bun",
    "codeium": PROFILE + r"\.codeium",
    "pm2": PROFILE + r"\.pm2",
    "lmstudio": PROFILE + r"\.lmstudio",
    "arduino15": PROFILE + r"\AppData\Local\Arduino15",
    "android-sdk": PROFILE + r"\AppData\Local\Android",
    "roblox-gdk": PROFILE + r"\AppData\Local\RobloxPCGDK",
    "perplexity": PROFILE + r"\AppData\Local\Perplexity",
    "minecraft": PROFILE + r"\AppData\Roaming\.minecraft",
    "nvidia-ota": r"C:\ProgramData\NVIDIA Corporation\NVIDIA App\UpdateFramework\ota-artifacts",
    "mimo-snapshots": PROFILE + r"\.mimo_storage",
}

def test_quick_recon() -> None:
    res = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for letter in ("C:", "M:"):
        u, _t, f = shutil.disk_usage(letter + "\\")
        res[letter] = {"used_gb": round(u / 1024**3, 1), "free_gb": round(f / 1024**3, 2)}
    states = {}
    for name, p in CANDS.items():
        st = {"exists": os.path.exists(p)}
        if st["exists"]:
            try:
                st["junction"] = os.path.realpath(p).lower() != p.lower()
            except OSError:
                st["junction"] = False
        states[name] = st
    res["candidates"] = states
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
