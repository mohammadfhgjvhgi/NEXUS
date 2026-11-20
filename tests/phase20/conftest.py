"""Phase-20 test package path setup — the repo root on sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(Path(__file__).resolve().parent)):
    if entry not in sys.path:
        sys.path.insert(0, entry)
