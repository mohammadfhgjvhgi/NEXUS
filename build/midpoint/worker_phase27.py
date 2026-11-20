# -*- coding: utf-8 -*-
"""worker_phase27.py — detached worker for PHASE 27 (Tray + Startup Production).

mover-v4 laws: heartbeats each stage · result file ALWAYS written · runs as a
detached Windows process (triggered once via code_run_tests spawn).

Stages:
  verify    — deployed nexus_ui.py AND nexus_launcher.py hashes match expected
  backup    — nexus_ui.py.pre27.bak + nexus_launcher.py.pre27.bak (idempotent)
  compile   — py_compile both files
  rebuild   — PyInstaller onefile (~200s)
  check     — NEXUS.exe --check (37/37 core)
  selftest  — NEXUS.exe --phase27-selftest (27.1–27.8, real tray lifecycle)
  certify   — PHASE-27-STATUS.md + PROJECT-CARD.md refresh (real disk values)
"""
from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent          # M:\NEXUS\build\midpoint
NEXUS = HERE.parent.parent                      # M:\NEXUS
PROOFS = NEXUS / "proofs"
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)
HB = RESULTS / "worker_phase27.hb.json"
RESULT = RESULTS / "worker_phase27.result.json"
LOG = RESULTS / "worker_phase27.log"
UI = HERE / "nexus_ui.py"
LN = HERE / "nexus_launcher.py"
EXPECTED_UI_SHA = "106e5ad2af04b72317aef554f3894960b3864dc79ec7ff5d2c4b3753d148bd6a"
EXPECTED_LN_SHA = "db354f0378aec0df23a797f41400030582dadeb476260962f8e7131e6a10a42c"
DIST_EXE = HERE / "dist" / "NEXUS.exe"


def hb(stage: str, note: str = "") -> None:
    try:
        HB.write_text(json.dumps(
            {"worker": "phase27", "stage": stage, "note": note[:200],
             "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "pid": os.getpid()}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def log(line: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")
    except OSError:
        pass


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list, timeout: int, cwd: Path = HERE) -> tuple[int, str]:
    log("$ " + " ".join(str(c) for c in cmd)[:220])
    proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd), timeout=timeout,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", shell=False)
    tail = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
    log(f"rc={proc.returncode} tail={tail[-300:]!r}")
    return proc.returncode, tail


def main() -> int:
    t0 = time.time()
    result: dict = {"worker": "phase27", "stages": {}, "utc_start":
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        # 1 verify -------------------------------------------------------
        hb("verify")
        got_ui = sha256_file(UI)
        got_ln = sha256_file(LN)
        ok_ui = (not EXPECTED_UI_SHA.startswith("%%")) and got_ui == EXPECTED_UI_SHA
        ok_ln = (not EXPECTED_LN_SHA.startswith("%%")) and got_ln == EXPECTED_LN_SHA
        result["stages"]["verify"] = {"ui": {"expected": EXPECTED_UI_SHA[:16],
                                             "got": got_ui[:16], "ok": ok_ui},
                                      "launcher": {"expected": EXPECTED_LN_SHA[:16],
                                                   "got": got_ln[:16], "ok": ok_ln}}
        if not (ok_ui and ok_ln):
            raise RuntimeError(f"hash mismatch ui={got_ui[:16]} ln={got_ln[:16]}")

        # 2 backup -------------------------------------------------------
        hb("backup")
        b1 = HERE / "nexus_ui.py.pre27.bak"
        b2 = HERE / "nexus_launcher.py.pre27.bak"
        if not b1.exists():
            shutil.copy2(UI, b1)
        if not b2.exists():
            shutil.copy2(LN, b2)
        result["stages"]["backup"] = [b1.name, b2.name]

        # 3 compile ------------------------------------------------------
        hb("compile")
        py_compile.compile(str(UI), doraise=True)
        py_compile.compile(str(LN), doraise=True)
        result["stages"]["compile"] = "ok"

        # 4 rebuild ------------------------------------------------------
        hb("rebuild", "PyInstaller starting")
        rc, tail = run([sys.executable, "-m", "PyInstaller", "NEXUS.exe.spec",
                        "--noconfirm", "--distpath", "dist",
                        "--workpath", "build"], timeout=2400)
        exe_ok = DIST_EXE.is_file()
        exe_sha = sha256_file(DIST_EXE) if exe_ok else ""
        result["stages"]["rebuild"] = {"rc": rc, "exe_bytes":
                                       DIST_EXE.stat().st_size if exe_ok else 0,
                                       "exe_sha256": exe_sha}
        if rc != 0 or not exe_ok:
            raise RuntimeError(f"rebuild failed rc={rc}: {tail[-300:]}")

        # 5 check --------------------------------------------------------
        hb("check")
        rc, tail = run([DIST_EXE, "--check"], timeout=300)
        result["stages"]["check"] = {"rc": rc, "tail": tail[-300:]}
        if rc != 0:
            raise RuntimeError(f"--check failed rc={rc}")

        # 6 selftest (PHASE 27 tray + startup lifecycle) ------------------
        hb("selftest", "running phase27 selftest (real tray lifecycle)")
        rc, tail = run([DIST_EXE, "--phase27-selftest"], timeout=1800)
        cert_path = PROOFS / "phase27_ui.json"
        cert = {}
        try:
            cert = json.loads(cert_path.read_text(encoding="utf-8"))
        except BaseException as exc:  # noqa: BLE001
            cert = {"read_error": f"{type(exc).__name__}: {exc}"}
        result["stages"]["selftest"] = {"rc": rc, "verdict": cert.get("verdict"),
                                        "sections_ok": cert.get("sections_ok"),
                                        "runtime_ok": cert.get("runtime_ok"),
                                        "seconds": cert.get("seconds")}
        if rc != 0 or cert.get("verdict") != "PASS":
            raise RuntimeError(f"phase27-selftest verdict={cert.get('verdict')} rc={rc} "
                               f"sections={json.dumps(cert.get('sections', {}), ensure_ascii=False)[:600]}")

        # 7 certify ------------------------------------------------------
        hb("certify")
        gate_sha = sha256_file(PROOFS / "midpoint_gate.json")
        p26_sha = sha256_file(PROOFS / "phase26_ui.json")
        p27_sha = sha256_file(PROOFS / "phase27_ui.json")
        secs = cert.get("sections", {})
        titles = ["ico", "tray", "states", "balloon", "menu", "autostart",
                  "raise", "exit"]
        status_md = (
            "# PHASE 27 — Tray + Startup Production (حالة حية)\n\n"
            f"- utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"- verdict: **{cert.get('verdict')}** · sections_ok={cert.get('sections_ok')} · "
            f"runtime_ok={cert.get('runtime_ok')} · core={cert.get('core_ok')} pkgs\n"
            f"- exe: {DIST_EXE.name} · {DIST_EXE.stat().st_size} B · sha256 {exe_sha[:32]}…\n"
            f"- الشهادة: proofs\\phase27_ui.json (8 أقسام بأدلة لكل قسم)\n"
            f"- اللقطات: proofs\\phase27\\sec_01..06_*.png (لقطة حية لكل مرحلة)\n"
            f"- البوابة مرتبطة: gate_cert_sha256={gate_sha[:32]}…\n\n"
            "| # | القسم | البرهان |\n|---|---|---|\n"
        )
        num = ["27.1 ico assets", "27.2 production tray", "27.3 state machine",
               "27.4 balloon NIF_INFO", "27.5 menu + single-instance raise",
               "27.6 autostart HKCU", "27.7 raise via 2nd process",
               "27.8 graceful exit"]
        for i, t in enumerate(titles):
            s = secs.get(t, {})
            status_md += (f"| {num[i]} | {t} | ok={s.get('ok')} · "
                          f"{json.dumps({k: v for k, v in s.items() if k != 'ok'}, ensure_ascii=False)[:120]} |\n")
        (HERE / "PHASE-27-STATUS.md").write_text(status_md, encoding="utf-8")

        card = (
            "# بطاقة المشروع — NEXUS Project Card (PHASE 27)\n"
            "- **المنتج**: NEXUS Windows Product v0.1 — NEXUS.exe حقيقي يعمل على جهاز Windows الحقيقي\n"
            "- **النواة**: v0.25.0 · 28 حزمة نواة · 37 وحدة تستورد بنجاح في كل إقلاع\n"
            "- **بوابة MIDPOINT**: 10/10 ✅ — شهادة موقعة `proofs\\midpoint_gate.json`\n"
            f"  (gate_cert_sha256={gate_sha[:32]}…)\n"
            "- **PHASE 26**: Desktop UI Production — 26.1–26.11 PASS · "
            f"`proofs\\phase26_ui.json` ({p26_sha[:20]}…) · 11 لقطة حية\n"
            "- **PHASE 27**: Tray + Startup Production — 27.1–27.8 PASS · "
            f"`proofs\\phase27_ui.json` ({p27_sha[:20]}…) · أيقونة .ico حقيقية + "
            "قائمة إنتاجية + autostart HKCU + single-instance raise + خروج نظيف\n"
            "- **القدرات (MIDPOINT-10)**: Full Stack · Android · Research · Coding · "
            "Automation · Computer · Documents — بطاقات ليست Modes مغلقة\n"
            "- **الجهاز**: i7-3770 (AVX بلا AVX2) · Ollama MODE A2 · GTX 750 Ti 4GB\n"
            "- **القوانين**: local-first · stdlib core · evidence or silence · القرص يحكم\n"
            f"- **التاريخ**: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"- **exe**: dist\\NEXUS.exe — {DIST_EXE.stat().st_size} B · sha256 {exe_sha}\n"
            "- **اللقطات**: `proofs\\phase26\\sec_01..11_*.png` · "
            "`proofs\\phase27\\sec_01..06_*.png`\n"
            "- **شهادات**: phase26_ui.json (PASS) · phase27_ui.json (PASS) · "
            "midpoint_cards.json (PASS)\n"
        )
        (PROOFS / "PROJECT-CARD.md").write_text(card, encoding="utf-8")
        result["stages"]["certify"] = {
            "status_md": str(HERE / "PHASE-27-STATUS.md"),
            "project_card": str(PROOFS / "PROJECT-CARD.md"),
            "phase27_cert_sha256": p27_sha}

        result["verdict"] = "PASS"
        hb("done")
    except BaseException as exc:  # noqa: BLE001
        result["verdict"] = "FAIL"
        result["error"] = f"{type(exc).__name__}: {exc}"[:400]
        result["traceback"] = traceback.format_exc()[-1200:]
        hb("fatal", result["error"])
    finally:
        result["seconds"] = round(time.time() - t0, 1)
        result["utc_end"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                              encoding="utf-8")
        except OSError:
            pass
        log(json.dumps(result, ensure_ascii=False)[:400])
    return 0 if result.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
