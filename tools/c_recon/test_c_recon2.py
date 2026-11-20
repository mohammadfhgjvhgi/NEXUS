"""C: recon v2 — granular map of C:\\Users (the 91 GB giant) with the
junction-death bug fixed (per-entry try), plus AppData breakdown and a
fuller big-file list.  Read-only.  Writes M:\\NEXUS\\proofs\\c_recon2.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

OUT = Path(r"M:\NEXUS\proofs\c_recon2.json")


def dir_size(path: str, big_files: list | None = None, min_big: int = 300 * 1024 * 1024) -> int:
    total = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            sz = entry.stat(follow_symlinks=False).st_size
                            total += sz
                            if big_files is not None and sz >= min_big:
                                big_files.append({"path": entry.path, "gb": round(sz / 1024**3, 3)})
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def safe_children_gb(root: str, floor_gb: float, big: list | None = None) -> dict:
    out = {}
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        p = os.path.join(root, name)
        try:
            if os.path.islink(p):
                continue
            if not os.path.isdir(p):
                continue
            sz = dir_size(p, big)
            if sz / 1024**3 >= floor_gb:
                out[p] = round(sz / 1024**3, 2)
        except OSError:
            continue
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def test_c_recon2() -> None:
    big: list = []
    result: dict = {}

    try:
        import shutil
        result["drives"] = {}
        for letter in ("C:", "M:"):
            u, _t, f = shutil.disk_usage(letter + "\\")
            result["drives"][letter] = {"used_gb": round(u / 1024**3, 1), "free_gb": round(f / 1024**3, 1)}
    except Exception as exc:  # noqa: BLE001
        result["drives"] = {"error": str(exc)}

    profiles: dict = {}
    try:
        for name in os.listdir("C:\\Users"):
            p = os.path.join("C:\\Users", name)
            try:
                if os.path.islink(p) or not os.path.isdir(p):
                    continue
                profiles[p] = round(dir_size(p, big) / 1024**3, 2)
            except OSError:
                continue
    except OSError:
        pass
    result["profiles_gb"] = dict(sorted(profiles.items(), key=lambda kv: -kv[1]))

    # for the largest real profile, one level down + AppData breakdown
    real = {k: v for k, v in profiles.items() if "All Users" not in k and "Default" not in k and v > 1}
    top = max(real, key=real.get) if real else None
    if top:
        result["profile"] = top
        result["profile_level1_gb"] = safe_children_gb(top, 0.2, big)
        appdata = os.path.join(top, "AppData", "Local")
        roaming = os.path.join(top, "AppData", "Roaming")
        result["appdata_local_gb"] = safe_children_gb(appdata, 0.3, big)
        result["appdata_roaming_gb"] = safe_children_gb(roaming, 0.3, big)
        # mimo storage total + snapshot breakdown
        mimo = os.path.join(top, ".mimo_storage")
        if os.path.isdir(mimo):
            result["mimo_storage_total_gb"] = round(dir_size(mimo, None) / 1024**3, 2)
            result["mimo_storage_parts_gb"] = safe_children_gb(mimo, 0.05, None)

    # focused candidate roots (exact sizes even if small)
    cand = {}
    if top:
        for rel in (".cache", ".cache\\huggingface", "Downloads", "Documents", "Desktop",
                    "Videos", "Pictures", "Music", ".ollama", ".lmstudio",
                    "AppData\\Local\\Temp", "AppData\\Local\\pip", "AppData\\Local\\npm-cache",
                    "AppData\\Local\\NVIDIA", "AppData\\Local\\NVIDIA Corporation", ".conda", "venvs"):
            p = os.path.join(top, rel)
            if os.path.isdir(p) and not os.path.islink(p):
                cand[p] = round(dir_size(p, None) / 1024**3, 2)
    nvidia_ota = r"C:\ProgramData\NVIDIA Corporation\NVIDIA App\UpdateFramework\ota-artifacts"
    if os.path.isdir(nvidia_ota):
        cand[nvidia_ota] = round(dir_size(nvidia_ota, None) / 1024**3, 2)
    epic = r"C:\ProgramData\Epic"
    if os.path.isdir(epic):
        cand[epic] = round(dir_size(epic, None) / 1024**3, 2)
    result["candidates_gb"] = dict(sorted(cand.items(), key=lambda kv: -kv[1]))

    big.sort(key=lambda x: -x["gb"])
    seen: set = set()
    uniq = []
    for b in big:
        if b["path"] not in seen:
            seen.add(b["path"])
            uniq.append(b)
    result["big_files_over_300mb"] = uniq[:60]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
