#!/usr/bin/env python3
"""Phase-17 device proof wrapper — runs ON the real box via code_run_tests.

pytest executes :mod:`live_research_ci` as a subprocess (the proof is a
script with its own exit code and six rungs) and asserts its outcome.
This is the sanctioned danger-1 execution path for the Windows proofs:
``code_run_tests`` (pytest in a project directory).

The proof writes a verdict JSON to ``M:\\NEXUS\\proofs\\phase17_live.json``
— but ONLY when ``M:\\`` is a real drive on this host.  The phase-15
lesson, kept: on a non-Windows host the literal ``M:\\...`` path is
*relative* and writing it would litter the repo with junk files.

Run (bridge, once):
    code_run_tests {project_root: M:\\NEXUS,
                    test_path: tests/phase17/test_device_proof.py}

Local/CI:  pytest tests/phase17/test_device_proof.py (device-only; CI
ignores it via --ignore-glob — the research-live job runs the raw
script directly; on a dev box the rungs still hold, only the verdict
file is skipped).
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

PROOF = Path(__file__).resolve().parent / "live_research_ci.py"
VERDICT = Path(r"M:\NEXUS\proofs\phase17_live.json")

_RUNG = re.compile(r"^\[(PASS|FAIL)\] (.+?)(?: — (.*))?$")


def _run_proof() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(PROOF)],
        capture_output=True,
        text=True,
        timeout=560,
        cwd=str(PROOF.parent.parent.parent),
    )


def test_device_live_proof() -> None:
    """The six rungs hold on a real machine — real network + real files."""
    proc = _run_proof()
    tail = proc.stdout.strip().splitlines()[-3:]
    print("\n".join(tail))
    if proc.returncode != 0:
        print("STDERR:", proc.stderr[-2000:])
    assert proc.returncode == 0, "the live proof rungs did not all hold"

    rungs = [
        {"ok": m.group(1) == "PASS", "label": m.group(2), "detail": m.group(3) or ""}
        for m in (_RUNG.match(line) for line in proc.stdout.splitlines())
        if m
    ]
    failed = [r["label"] for r in rungs if not r["ok"]]
    assert not failed, f"failed rungs: {failed}"
    assert len(rungs) == 6, f"expected 6 rungs, got {len(rungs)}"

    # ---- verdict: only on a host where M:\ is a real drive (anchor check)
    if not VERDICT.anchor or not Path(VERDICT.anchor).exists():
        print("  [WARN] verdict not written — M:\\ is not a real drive on this host")
        return
    verdict = {
        "phase": 17,
        "verdict": "PASS",
        "rungs_passed": sum(1 for r in rungs if r["ok"]),
        "rungs_failed": 0,
        "rungs": rungs,
        "nexus_version": "0.17.0",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }
    try:
        VERDICT.parent.mkdir(parents=True, exist_ok=True)
        VERDICT.write_text(
            json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"verdict written: {VERDICT}")
    except OSError as exc:
        print(f"  [WARN] verdict not written: {exc}")
