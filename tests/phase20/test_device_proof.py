#!/usr/bin/env python3
"""Phase-20 device proof wrapper — runs ON the real box via code_run_tests.

pytest executes :mod:`live_verification_ci` as a subprocess (the proof
is a script with its own exit code and ten rungs) and asserts its
outcome, then writes the verdict to ``M:\\NEXUS\\proofs\\phase20_live.json``
— but ONLY when ``M:\\`` is a real drive on this host (the phase-15
lesson, kept).

On the device, rung 5 is STRICT: no FAIL and no ERROR across the nine
domains — the Windows domain's probes (platform · checkpoint ·
powershell) must really PASS there, not SKIP.

Run (bridge, once):
    code_run_tests {project_root: M:\\NEXUS,
                    test_path: tests/phase20/test_device_proof.py}

Local/CI:  pytest tests/phase20/test_device_proof.py (device-only; CI
ignores it via --ignore-glob — the verification-live job runs the raw
script).
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

PROOF = Path(__file__).resolve().parent / "live_verification_ci.py"
VERDICT = Path(r"M:\NEXUS\proofs\phase20_live.json")

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
    """The ten rungs hold on a real machine — real probes, real repair."""
    proc = _run_proof()
    tail = proc.stdout.strip().splitlines()[-4:]
    print("\n".join(tail))
    if proc.returncode != 0:
        print("STDERR:", proc.stderr[-2000:])
    assert proc.returncode == 0, "the live proof rungs did not all hold"

    rungs = [
        {"ok": m.group(1) == "PASS", "label": m.group(2), "detail": m.group(3) or ""}
        for m in (_RUNG.match(line) for line in proc.stdout.splitlines())
        if m
    ]
    failed = [str(r["label"]) for r in rungs if not r["ok"]]
    assert not failed, f"failed rungs: {failed}"
    assert len(rungs) == 10, f"expected 10 rungs, got {len(rungs)}"

    if platform.system() == "Windows":
        # strict on the real box: no honest-off-Windows SKIP may stand in
        # for the Windows facts there — the platform probe must really PASS.
        for rung in rungs:
            assert "judged on the real box" not in str(rung["detail"])

    # ---- verdict: only on a host where M:\ is a real drive (anchor check)
    if not VERDICT.anchor or not Path(VERDICT.anchor).exists():
        print("  [WARN] verdict not written — M:\\ is not a real drive on this host")
        return
    verdict = {
        "phase": 20,
        "section": "Verification Engine",
        "verdict": "PASS",
        "rungs_passed": sum(1 for r in rungs if r["ok"]),
        "rungs_failed": 0,
        "rungs": rungs,
        "nexus_version": "0.20.0",
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
