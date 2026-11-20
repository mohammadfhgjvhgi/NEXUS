#!/usr/bin/env python3
"""Phase-12 device proof wrapper — runs ON the real box via code_run_tests.

pytest executes :mod:`live_proof_device` as a subprocess (the proof is a
script with its own verdict JSON and exit code) and asserts its outcome.
This is the sanctioned danger-1 execution path for the Windows proofs:
``code_run_tests`` (pytest in a project directory).

Run (bridge):  code_run_tests {project_root: M:\\NEXUS,
                              test_path: tests/phase12/test_device_proof.py}
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROOF = Path(__file__).resolve().parent / "live_proof_device.py"
VERDICT = Path(r"M:\NEXUS\proofs\phase12_live.json")


def test_device_live_proof() -> None:
    """The §12 exit gate on real Windows — the box is the judge."""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(PROOF)],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=str(PROOF.parent.parent.parent),
    )
    tail = proc.stdout.strip().splitlines()[-3:]
    print("\n".join(tail))
    if proc.returncode != 0:
        print("STDERR:", proc.stderr[-2000:])
    assert proc.returncode == 0, f"device proof failed: {tail}"
    report = json.loads(VERDICT.read_text(encoding="utf-8"))
    failed = {
        key: value
        for key, value in report.items()
        if isinstance(value, dict) and value.get("ok") is False
    }
    assert not failed, f"failed checks: {list(failed)}"
    n = sum(1 for v in report.values() if isinstance(v, dict))
    print(f"device verdict: {n} checks, 0 failed")
