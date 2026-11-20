#!/usr/bin/env python3
"""Phase-24 device proof wrapper — runs ON the real box via code_run_tests.

pytest executes :mod:`live_orchestration_ci` as a subprocess (the proof
is a script with its own exit code and eleven rungs) and asserts its
outcome, then writes the verdict to ``M:\\NEXUS\\proofs\\phase24_live.json``
— but ONLY when ``M:\\`` is a real drive on this host (the phase-15
lesson, kept).

Run (bridge, once):
    code_run_tests {project_root: M:\\NEXUS,
                    test_path: tests/phase24/test_device_proof.py}

Local/CI:  pytest tests/phase24/test_device_proof.py (device-only; CI
ignores it via --ignore-glob — the agents-live job runs the raw
script).
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from pathlib import Path

PROOF = Path(__file__).resolve().parent / "live_orchestration_ci.py"
VERDICT = Path(r"M:\NEXUS\proofs\phase24_live.json")

_RUNG = re.compile(r"^\[(PASS|FAIL)\] (.+?)(?: — (.*))?$", re.MULTILINE)


def _run_proof() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(PROOF)],
        capture_output=True,
        text=True,
        timeout=560,
        cwd=str(PROOF.parent.parent.parent),
    )


def test_device_live_proof() -> None:
    """The eleven rungs hold on a real machine — real threads, real walls."""
    completed = _run_proof()
    out = completed.stdout + completed.stderr
    rungs = _RUNG.findall(out)
    assert rungs, f"no rungs parsed from the live proof:\n{out[-1200:]}"
    failed = [label for status, label, _ in rungs if status == "FAIL"]
    assert not failed, f"failed rungs: {failed}\n{out[-1200:]}"
    assert f"PROOF: {len(rungs)}/{len(rungs)} rungs passed" in out
    assert completed.returncode == 0

    # Windows-only: seal the verdict on the real drive (phase-15 lesson)
    if platform.system() == "Windows" and Path("M:\\").exists():
        VERDICT.parent.mkdir(parents=True, exist_ok=True)
        verdict = {
            "phase": 24,
            "section": "Multi-Agent Orchestration (New Plan §24)",
            "verdict": "PASS",
            "rungs": len(rungs),
            "passed": len(rungs),
            "labels": [label for _, label, _ in rungs],
            "host": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
        }
        VERDICT.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        assert "PASS" in VERDICT.read_text(encoding="utf-8")
