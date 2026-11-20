"""C: drive recon — what consumes space, written as a pytest file so the
tunnel tool `code_run_tests` can execute it (code_run_powershell is
localhost-only by policy).

Writes M:\\NEXUS\\proofs\\c_recon.json — the caller reads it back.
Never deletes anything. Read-only walk (os.scandir, no symlink follow).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

OUT = Path(r"M:\NEXUS\proofs\c_recon.json")

SKIP_DIRS = {"windows", "program files", "program files (x86)", "$recycle.bin",
             "system volume information", "recovery", "dumpstacklogs.tmp"}


def dir_size(path: str, big_files: list, min_big: int) -> int:
    total = 0
    try:
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
                                if sz >= min_big:
                                    big_files.append(
                                        {"path": entry.path, "gb": round(sz / 1024**3, 2)})
                            elif entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception:
        pass
    return total


def test_c_recon() -> None:
    drives = {}
    for letter in ("C:", "M:"):
        total, _free = 0, 0
        try:
            import shutil
            u, _t, f = shutil.disk_usage(letter + "\\")
            drives[letter] = {"used_gb": round(u / 1024**3, 1), "free_gb": round(f / 1024**3, 1)}
        except Exception as exc:  # noqa: BLE001
            drives[letter] = {"error": str(exc)}

    big: list = []
    top = {}
    # root-level directories (excluding system giants measured separately)
    for entry in os.scandir("C:\\"):
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name.lower() in SKIP_DIRS:
                continue
            top[entry.path] = round(dir_size(entry.path, big, 300 * 1024 * 1024) / 1024**3, 2)
        except OSError:
            continue

    # user-profile second level
    users2 = {}
    try:
        for uentry in os.scandir("C:\\Users"):
            if not uentry.is_dir(follow_symlinks=False):
                continue
            for entry in os.scandir(uentry.path):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        sz = dir_size(entry.path, big, 300 * 1024 * 1024)
                        if sz / 1024**3 >= 0.5:
                            users2[entry.path] = round(sz / 1024**3, 2)
                except OSError:
                    continue
    except OSError:
        pass

    # programdata second level
    pd2 = {}
    try:
        for entry in os.scandir("C:\\ProgramData"):
            try:
                if entry.is_dir(follow_symlinks=False):
                    sz = dir_size(entry.path, big, 300 * 1024 * 1024)
                    if sz / 1024**3 >= 0.3:
                        pd2[entry.path] = round(sz / 1024**3, 2)
            except OSError:
                continue
    except OSError:
        pass

    big.sort(key=lambda x: -x["gb"])
    result = {
        "drives": drives,
        "c_root_dirs_gb": dict(sorted(top.items(), key=lambda kv: -kv[1])[:15]),
        "c_users_subdirs_gb": dict(sorted(users2.items(), key=lambda kv: -kv[1])[:20]),
        "c_programdata_subdirs_gb": dict(sorted(pd2.items(), key=lambda kv: -kv[1])[:15]),
        "big_files_over_300mb": big[:40],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
