"""Read-only repo layout recon -> results/nexus_dirlist.json (no side effects)."""
from __future__ import annotations

import json
import os
from pathlib import Path

OUT = Path(r"M:\NEXUS\tools\c_relief\results\nexus_dirlist.json")
ROOTS = [
    r"M:\NEXUS",
    r"M:\NEXUS\docs",
    r"M:\NEXUS\docs\reference",
    r"M:\NEXUS\docs\nexus-knowledge",
    r"M:\NEXUS\nexus-knowledge",
    r"M:\NEXUS\nexus",
    r"M:\NEXUS\product",
    r"M:\NEXUS\tests",
    r"M:\NEXUS\tools",
]


def test_dirlist() -> None:
    out: dict = {}
    for root in ROOTS:
        try:
            entries = sorted(os.listdir(root))[:300]
            out[root] = entries
        except OSError as exc:
            out[root] = f"ERR {exc}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    assert OUT.exists()
