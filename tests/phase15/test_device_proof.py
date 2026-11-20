#!/usr/bin/env python3
"""Phase-15 device proof wrapper — runs ON the real box via code_run_tests.

pytest executes :mod:`live_proof_device` as a subprocess (the proof is a
script with its own verdict JSON and exit code) and asserts its outcome.
This is the sanctioned danger-1 execution path for the Windows proofs:
``code_run_tests`` (pytest in a project directory).

The proof is split in two pytest nodes because the tunnel gatekeeper caps
a single bridge call at 60s — the user's own directive: split the task
when splitting is faster and better:

* ``test_part_a_fast_checks``   — the five behavior checks (~25s)
* ``test_part_b_self_analysis`` — NEXUS analyzes itself (~30s) and the
  merged verdict must be 6/6 green with no pending marker.

Run (bridge, twice):
    code_run_tests {project_root: M:\\NEXUS,
                    test_path: tests/phase15/test_device_proof.py::test_part_a_fast_checks}
    code_run_tests {project_root: M:\\NEXUS,
                    test_path: tests/phase15/test_device_proof.py::test_part_b_self_analysis}

Local/CI:  pytest tests/phase15/test_device_proof.py (device-only; CI
ignores it via --ignore-glob, the sandbox honestly fails part b — no
M:\\NEXUS here).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROOF = Path(__file__).resolve().parent / "live_proof_device.py"
VERDICT = Path(r"M:\NEXUS\proofs\phase15_live.json")
PENDING_KEY = "__part_b__"


def _run_proof(part: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(PROOF), "--part", part],
        capture_output=True,
        text=True,
        timeout=560,
        cwd=str(PROOF.parent.parent.parent),
    )


def _report(proc: subprocess.CompletedProcess[str]) -> None:
    tail = proc.stdout.strip().splitlines()[-3:]
    print("\n".join(tail))
    if proc.returncode != 0:
        print("STDERR:", proc.stderr[-2000:])


def _checks(report: dict) -> dict[str, dict]:
    return {k: v for k, v in report.items() if isinstance(v, dict) and "ok" in v}


def test_part_a_fast_checks() -> None:
    """The five behavior checks — the box is the judge."""
    proc = _run_proof("a")
    _report(proc)
    assert proc.returncode == 0, "part a failed"
    report = json.loads(VERDICT.read_text(encoding="utf-8"))
    checks = _checks(report)
    failed = [k for k, v in checks.items() if v.get("ok") is False]
    assert not failed, f"part a failed checks: {failed}"
    assert len(checks) == 5, f"expected 5 checks, got {len(checks)}"
    assert report.get(PENDING_KEY) == "pending", "part b marker missing"
    print(f"part a verdict: {len(checks)} checks, 0 failed")


def test_part_b_self_analysis() -> None:
    """NEXUS analyzes its own codebase — the merged verdict must be 6/6."""
    proc = _run_proof("b")
    _report(proc)
    assert proc.returncode == 0, "part b failed"
    report = json.loads(VERDICT.read_text(encoding="utf-8"))
    checks = _checks(report)
    failed = [k for k, v in checks.items() if v.get("ok") is False]
    assert not failed, f"merged verdict failed checks: {failed}"
    assert PENDING_KEY not in report, "part b never merged (pending marker left)"
    assert len(checks) == 6, f"expected merged 6 checks, got {len(checks)}"
    assert "the developer agent analyzes M:\\NEXUS itself" in checks, "self check missing"
    print(f"merged device verdict: {len(checks)} checks, 0 failed")
