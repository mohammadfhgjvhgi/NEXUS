#!/usr/bin/env python3
"""Phase-21 device proof wrapper — runs ON the real box via code_run_tests.

pytest executes :mod:`live_security_ci` as a subprocess (the proof
is a script with its own exit code and ten rungs) and asserts its
outcome, then writes the verdict to ``M:\\NEXUS\\proofs\\phase21_live.json``
— but ONLY when ``M:\\`` is a real drive on this host (the phase-15
lesson, kept).

The §21.9 trivy rung is honest in both directions: a real trivy on
the box means MODE A scans with real findings; an absent trivy means
the MODE B honest note.  Set ``NEXUS_REQUIRE_TRIVY=1`` to make MODE A
strict (the CI job does).

Run (bridge, once):
    code_run_tests {project_root: M:\\NEXUS,
                    test_path: tests/phase21/test_device_proof.py}

Local/CI:  pytest tests/phase21/test_device_proof.py (device-only; CI
ignores it via --ignore-glob — the security-live job runs the raw
script).
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

PROOF = Path(__file__).resolve().parent / "live_security_ci.py"
VERDICT = Path(r"M:\NEXUS\proofs\phase21_live.json")

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
    """The ten rungs hold on a real machine — real gates, real vault."""
    # Optional MODE A: if a trivy binary was staged on the box, hand it
    # to the scanner through the documented env seam (the environment
    # is the judge — absent trivy keeps the honest MODE B rung).  The
    # cache rides M: too — the box's C: has no room for the ~70MB DB.
    staged = Path(r"M:\NEXUS\tools-bin\trivy.exe")
    if staged.is_file():
        os.environ.setdefault("NEXUS_TRIVY_BINARY", str(staged))
        os.environ.setdefault(
            "TRIVY_CACHE_DIR", r"M:\NEXUS\tools-bin\trivy-cache"
        )
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
            "phase": 21,
            "section": "Security System (New Plan §21)",
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
