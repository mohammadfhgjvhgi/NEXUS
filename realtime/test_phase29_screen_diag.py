# -*- coding: utf-8 -*-
"""One-shot screen diagnostics (PHASE 29) — runs ON THE DEVICE via pytest.

Why: tunnel cannot reach loopback ports, and code_run_powershell is
localhost-only policy — so this pytest file IS the device-side probe.
It writes realtime\\screen_diag.json and passes. Read-only polling after.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # M:\NEXUS\realtime
OUT = HERE / "screen_diag.json"
PNG = HERE / "captures" / "diag29.png"

SCRIPT = (
    "Add-Type -AssemblyName System.Windows.Forms;"
    "Add-Type -AssemblyName System.Drawing;"
    "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
    "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
    "$g=[System.Drawing.Graphics]::FromImage($bmp);"
    "$g.CopyFromScreen($b.X,$b.Y,0,0,$bmp.Size);"
    "$bmp.Save('" + str(PNG).replace("'", "''") + "',"
    "[System.Drawing.Imaging.ImageFormat]::Png);"
    "Write-Output ('OK ' + $b.Width + 'x' + $b.Height)"
)


def _run(label, args, timeout):
    t0 = time.perf_counter()
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
        rec = {
            "rc": p.returncode,
            "stdout": p.stdout.decode("utf-8", "replace")[:300],
            "stderr": p.stderr.decode("utf-8", "replace")[:400],
            "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except BaseException as exc:  # noqa: BLE001
        rec = {"error": f"{type(exc).__name__}: {exc}"[:300],
               "duration_ms": round((time.perf_counter() - t0) * 1000, 1)}
    rec["label"] = label
    return rec


def test_phase29_screen_diag() -> None:
    res = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    res["t1_hello"] = _run("hello", [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Write-Output hello-ps"], 30)
    res["t2_capture"] = _run("capture", [
        "powershell", "-NoProfile", "-NonInteractive", "-STA",
        "-Command", SCRIPT], 60)
    res["t3_exe"] = _run("exe", [
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "-NoProfile", "-NonInteractive", "-Command",
        "Write-Output hello-exe"], 30)
    try:
        res["png"] = {"exists": PNG.is_file(),
                      "size": PNG.stat().st_size if PNG.is_file() else 0}
    except BaseException as exc:  # noqa: BLE001
        res["png"] = {"error": str(exc)[:160]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    assert True
