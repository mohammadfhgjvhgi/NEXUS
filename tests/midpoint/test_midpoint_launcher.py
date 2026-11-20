"""MIDPOINT GATE check #1 — the Launcher boots the whole core honestly.

Runs nexus_launcher.py --check as a real subprocess and requires:
  * exit code 0
  * verdict PASS (all 28+ core packages import)
  * a sealed boot certificate on disk (proofs\\midpoint_boot.json)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(r"M:\NEXUS\build\midpoint")
LAUNCHER = HERE / "nexus_launcher.py"
CERT = Path(r"M:\NEXUS\proofs\midpoint_boot.json")


def test_midpoint_launcher_boot() -> None:
    assert LAUNCHER.exists(), f"launcher missing: {LAUNCHER}"
    proc = subprocess.run(
        [sys.executable, str(LAUNCHER), "--check"],
        capture_output=True, text=True, timeout=300, cwd=str(HERE))
    assert proc.returncode == 0, (
        f"launcher check failed rc={proc.returncode}\n"
        f"stdout={proc.stdout[-800:]}\nstderr={proc.stderr[-800:]}")
    assert CERT.exists(), "boot certificate not written"
    cert = json.loads(CERT.read_text(encoding="utf-8"))
    assert cert.get("verdict") == "PASS", f"verdict={cert.get('verdict')}"
    summary = cert.get("core_summary") or {}
    assert summary.get("err") == 0, f"core probe errors: {cert.get('core_probes', {}).get('err')}"
    assert summary.get("ok", 0) >= 28, f"expected >=28 core packages, got {summary.get('ok')}"
