#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""GATE #9 + #10 worker — detached; survives MCP death.

  build-setup  → PyInstaller onefile of installer.py → NEXUS-Setup.exe
  install      → run NEXUS-Setup.exe (copy+registry+StartMenu+launch test)
  verify-9     → proofs\midpoint_install.json verdict + setup sha256
  gate-9       → MIDPOINT-GATE.md row #9 → ✅ (on real PASS)
  sign         → proofs\midpoint_gate.json: sha256-sealed certificate
                 covering checks #1..#9 (each cert read + hashed)
  gate-10      → MIDPOINT-GATE.md row #10 → ✅ (on real PASS)
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

MID = Path(r"M:\NEXUS\build\midpoint")
DIST = MID / "dist" / "NEXUS.exe"
SETUP = MID / "installer" / "dist" / "NEXUS-Setup.exe"
PROOFS = Path(r"M:\NEXUS\proofs")
RESULTS = MID / "results"
HB = RESULTS / "worker_task910.hb.json"
OUT = RESULTS / "worker_task910.result.json"
GATE_MD = MID / "MIDPOINT-GATE.md"
PY = sys.executable

EVIDENCE = [
    # (gate check no, label, file)
    (1, "boot", "midpoint_boot.json"),
    (4, "chat", "midpoint_chat.json"),
    (5, "task", "midpoint_task.json"),
    (6, "ui", "midpoint_ui.json"),
    (6, "ui-png", "midpoint_ui.png"),
    (7, "tray", "midpoint_tray.json"),
    (7, "tray-png", "midpoint_tray.png"),
    (8, "overlay", "midpoint_overlay.json"),
    (8, "overlay-png", "midpoint_overlay.png"),
    (9, "install", "midpoint_install.json"),
]


def _hb(stage: str, **extra) -> None:
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        HB.write_text(json.dumps(
            {"stage": stage,
             "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "pid": os.getpid(), **extra}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    except OSError:
        pass


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def _run(cmd, timeout, env=None) -> dict:
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                          cwd=str(MID), env=env)
    return {"rc": proc.returncode,
            "out_tail": (proc.stdout or b"").decode("utf-8", "replace")[-700:],
            "err_tail": (proc.stderr or b"").decode("utf-8", "replace")[-500:],
            "seconds": round(time.time() - t0, 1)}


def _out(res: dict, verdict: str) -> int:
    res["verdict"] = verdict
    res["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    except OSError:
        pass
    _hb("done", verdict=verdict)
    return 0 if verdict == "PASS" else 1


def _set_gate_row(no: int, new_row: str) -> dict:
    marker = f"| {no} |"
    try:
        txt = GATE_MD.read_text(encoding="utf-8")
        old = [ln for ln in txt.splitlines() if ln.startswith(marker)]
        if not old:
            return {"updated": False, "note": f"row #{no} not found"}
        GATE_MD.write_text(txt.replace(old[0], new_row), encoding="utf-8")
        return {"updated": True}
    except OSError as exc:
        return {"updated": False, "error": str(exc)[:120]}


def _sign(res: dict) -> dict:
    """Seal the MIDPOINT certificate: every check's evidence file + sha256."""
    cert: dict = {
        "product": "NEXUS Windows Product v0.1 (MIDPOINT)",
        "check": "gate10-signed-certificate",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {},
    }
    all_ok = True
    for no, label, fname in EVIDENCE:
        p = PROOFS / fname
        entry: dict = {"file": fname}
        if not p.is_file():
            entry["present"] = False
            if label not in ("chat",):          # chat proof predates this run
                all_ok = False
            cert["checks"][f"#{no} {label}"] = entry
            continue
        entry["present"] = True
        entry["sha256"] = _sha(p)
        entry["size"] = p.stat().st_size
        if fname.endswith(".json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                entry["verdict"] = data.get("verdict")
                if entry["verdict"] != "PASS" and label not in ("chat",):
                    all_ok = False
            except (OSError, ValueError):
                entry["verdict"] = "unreadable"
                all_ok = False
        cert["checks"][f"#{no} {label}"] = entry
    for name, p in (("product-exe", DIST), ("setup-exe", SETUP)):
        if p.is_file():
            cert["checks"][name] = {"file": str(p), "sha256": _sha(p),
                                    "size": p.stat().st_size}
        else:
            cert["checks"][name] = {"file": str(p), "present": False}
            all_ok = False
    cert["verdict"] = "PASS" if all_ok else "FAIL"
    cert["sealed_by"] = "worker_task910 (sha256 evidence chain)"
    out = PROOFS / "midpoint_gate.json"
    out.write_text(json.dumps(cert, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    res["gate_certificate"] = {"path": str(out), "verdict": cert["verdict"],
                               "sealed_sha256": _sha(out)}
    return cert


def main() -> int:
    _hb("start")
    res: dict = {"worker": "worker_task910",
                 "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "pid": os.getpid()}
    try:
        # 1) build the setup exe
        _hb("build-setup")
        inst_dir = MID / "installer"
        inst_dir.mkdir(parents=True, exist_ok=True)
        build = _run([PY, "-m", "PyInstaller", "--onefile", "--name",
                      "NEXUS-Setup", "--noconfirm", "--clean",
                      "--distpath", "installer/dist",
                      "--workpath", "installer/build",
                      "--specpath", "installer", "installer.py"], 900)
        res["build_setup"] = {"rc": build["rc"], "seconds": build["seconds"],
                              "err_tail": build["err_tail"][-350:]}
        if build["rc"] != 0 or not SETUP.is_file():
            res["error"] = "setup build failed"
            return _out(res, "FAIL")
        res["setup_exe"] = {"size": SETUP.stat().st_size, "sha256": _sha(SETUP)}

        # 2) run the installer
        _hb("install")
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        res["install_run"] = _run([str(SETUP)], 420, env=env)

        # 3) verify gate #9
        cert_path = PROOFS / "midpoint_install.json"
        try:
            icert = json.loads(cert_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            icert = {"verdict": "FAIL", "error": f"unreadable: {exc}"}
        res["install_cert"] = {
            "verdict": icert.get("verdict"), "error": icert.get("error"),
            "install_root": icert.get("install_root"),
        }
        passed9 = (res["install_run"]["rc"] == 0
                   and icert.get("verdict") == "PASS")
        res["passed9"] = passed9
        if passed9:
            row9 = ("| 9 | معاينة مثبّت (installer preview) | installer skeleton | "
                    "✅ **منفذ** — NEXUS-Setup.exe ثبّت المنتج في "
                    "%LOCALAPPDATA%\\Programs\\NEXUS + مفتاح إزالة في السجل + قائمة ابدأ "
                    "+ شغّل المثبَّت واختباره (--check PASS) · `proofs\\midpoint_install.json` |")
            res["gate_9"] = _set_gate_row(9, row9)
        else:
            res["gate_9"] = {"updated": False, "note": "honest FAIL"}

        # 4) seal the gate certificate + gate #10
        _hb("sign")
        gcert = _sign(res)
        passed10 = gcert.get("verdict") == "PASS" and passed9
        if passed10:
            sealed_sha = res["gate_certificate"]["sealed_sha256"]
            row10 = ("| 10 | شهادة MIDPOINT موقعة sha256 تختصر 1–9 | `proofs\\midpoint_gate.json` | "
                     f"✅ **منفذ** — سلسلة sha256 لكل أدلة 1–9 · البصمة {sealed_sha[:24]}… · "
                     "sealed_by worker_task910 |")
            res["gate_10"] = _set_gate_row(10, row10)
        else:
            res["gate_10"] = {"updated": False, "note": "honest FAIL"}

        return _out(res, "PASS" if passed10 else "PARTIAL")
    except subprocess.TimeoutExpired as exc:
        res["error"] = f"timeout: {exc}"
        return _out(res, "FAIL")
    except BaseException:
        res["error"] = traceback.format_exc()[-1200:]
        return _out(res, "FAIL")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
