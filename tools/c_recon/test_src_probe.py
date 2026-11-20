"""src-state probe for arduino15."""
from __future__ import annotations
import json, os, time
from pathlib import Path

OUT = Path(r"M:\NEXUS\tools\c_relief\results\src_probe.json")
SRC = r"C:\Users\MohandsMohammad\AppData\Local\Arduino15"

def tree_bytes(root: str) -> tuple[int, int]:
    total, count = 0, 0
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                            count += 1
                        elif e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return total, count

def test_probe() -> None:
    total, count = tree_bytes(SRC)
    OUT.write_text(json.dumps({"gb": round(total/2**30, 3), "files": count,
                               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}),
                   encoding="utf-8")
    assert OUT.exists()
