# -*- coding: utf-8 -*-
"""worker_phase28.py — detached worker for PHASE 28 (Remote Web).

mover-v4 laws: heartbeats each stage · result file ALWAYS written · runs as a
detached Windows process (triggered once via code_run_tests spawn).

Stages:
  verify    — 7 deployed files match expected CRLF sha256
              (nexus_ui · nexus_launcher · nexus_remote_gateway ·
               web/index.html · web/app.css · web/app.js · pages.yml)
  backup    — *.pre28.bak for ui/launcher/spec (idempotent)
  compile   — py_compile ui + launcher + gateway
  rebuild   — PyInstaller onefile (~200s)
  check     — NEXUS.exe --check (37/37 core)
  selftest  — NEXUS.exe --phase28-selftest (real HTTP loop, 13 sections)
  certify   — PHASE-28-STATUS.md + PROJECT-CARD.md + remote README-DEPLOY
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
HB = RESULTS / "worker_phase28.hb.json"
RESULT = RESULTS / "worker_phase28.result.json"
LOG = RESULTS / "worker_phase28.log"
UI = HERE / "nexus_ui.py"
LN = HERE / "nexus_launcher.py"
GW = HERE / "nexus_remote_gateway.py"
SPEC = HERE / "NEXUS.exe.spec"
DIST_EXE = HERE / "dist" / "NEXUS.exe"

EXPECTED = {
    "ui": "c77f6b4d5bf628c4ca8349864405ea0f406b11cf32dab94ac12348b55bee04d2",
    "launcher": "da9b66c2e9a958e50975f700c07e0e864165fda039a07137a51bfc400c2c56a0",
    "gateway": "61c2de7ce876363f2c8eafb6cf17b55bc5e6691c806dd5d71da963d604f85fac",
    "index": "5f47b69cf432d03f2ca797025701fcea616e32052d40cc9f07015f40331134e3",
    "css": "69b179305ca8015fa94d3424a6751e79a841d5aec878d7343de25af96f39ad35",
    "js": "67c1fbd55516e87673ef77eb364053c41d1fb28ae663d155425267e5ffce6d38",
    "pages": "db0fbebb686cc7080179017c849ec9e03c15a2cd48f4c97161d15153f97a165e",
}


def hb(stage: str, note: str = "") -> None:
    try:
        HB.write_text(json.dumps(
            {"worker": "phase28", "stage": stage, "note": note[:200],
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
    result: dict = {"worker": "phase28", "stages": {}, "utc_start":
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        # 1 verify -------------------------------------------------------
        hb("verify")
        files = {
            "ui": UI,
            "launcher": LN,
            "gateway": GW,
            "index": NEXUS / "remote" / "web" / "index.html",
            "css": NEXUS / "remote" / "web" / "app.css",
            "js": NEXUS / "remote" / "web" / "app.js",
            "pages": NEXUS / ".github" / "workflows" / "pages.yml",
        }
        verify = {}
        for key, path in files.items():
            exp = EXPECTED[key]
            got = sha256_file(path)
            ok = (not exp.startswith("%%")) and got == exp
            verify[key] = {"expected": exp[:16], "got": got[:16], "ok": ok}
            if not ok:
                raise RuntimeError(f"hash mismatch {key}: {got[:16]} != {exp[:16]}")
        result["stages"]["verify"] = verify

        # 2 backup -------------------------------------------------------
        hb("backup")
        backups = []
        for src in (UI, LN, SPEC):
            bak = src.with_suffix(src.suffix + ".pre28.bak")
            if not bak.exists():
                shutil.copy2(src, bak)
            backups.append(bak.name)
        result["stages"]["backup"] = backups

        # 3 compile ------------------------------------------------------
        hb("compile")
        py_compile.compile(str(UI), doraise=True)
        py_compile.compile(str(LN), doraise=True)
        py_compile.compile(str(GW), doraise=True)
        result["stages"]["compile"] = "ok"

        # 4 rebuild ------------------------------------------------------
        hb("rebuild", "PyInstaller starting")
        rc, tail = run([sys.executable, "-m", "PyInstaller", SPEC.name,
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

        # 6 selftest (real HTTP loop — gateway + executor + security) ------
        hb("selftest", "running phase28 remote selftest")
        rc, tail = run([DIST_EXE, "--phase28-selftest"], timeout=1800)
        cert_path = PROOFS / "phase28_remote.json"
        cert = {}
        try:
            cert = json.loads(cert_path.read_text(encoding="utf-8"))
        except BaseException as exc:  # noqa: BLE001
            cert = {"read_error": f"{type(exc).__name__}: {exc}"}
        result["stages"]["selftest"] = {"rc": rc, "verdict": cert.get("verdict"),
                                        "sections_ok": cert.get("sections_ok"),
                                        "seconds": cert.get("seconds"),
                                        "port": cert.get("port")}
        if rc != 0 or cert.get("verdict") != "PASS":
            raise RuntimeError(f"phase28-selftest verdict={cert.get('verdict')} rc={rc} "
                               f"sections={json.dumps(cert.get('sections', {}), ensure_ascii=False)[:600]}")

        # 7 certify ------------------------------------------------------
        hb("certify")
        gate_sha = sha256_file(PROOFS / "midpoint_gate.json")
        p26_sha = sha256_file(PROOFS / "phase26_ui.json")
        p27_sha = sha256_file(PROOFS / "phase27_ui.json")
        p28_sha = sha256_file(PROOFS / "phase28_remote.json")
        secs = cert.get("sections", {})
        order = ["health", "auth", "status", "pause", "resume", "checkpoint",
                 "task", "chat", "files_push", "files_pull", "security",
                 "static", "cors"]
        labels = ["28.0 health", "28.2 auth 401×2", "28.2 status",
                  "28.3 pause", "28.3 resume", "28.3 checkpoint",
                  "28.3 task (M4 real)", "28.3 chat honest",
                  "28.4 push sha", "28.4 pull sha", "28.4 traversal blocked",
                  "28.1 static served", "28.2 CORS"]
        status_md = (
            "# PHASE 28 — Remote Web (حالة حية)\n\n"
            f"- utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"- verdict: **{cert.get('verdict')}** · sections_ok={cert.get('sections_ok')} "
            f"({len(secs)} قسمًا) · port={cert.get('port')}\n"
            f"- exe: {DIST_EXE.name} · {DIST_EXE.stat().st_size} B · sha256 {exe_sha[:32]}…\n"
            f"- الشهادة: proofs\\phase28_remote.json\n"
            f"- الواجهة: remote\\web\\ (index.html + app.css + app.js — جاهزة لـGitHub Pages)\n"
            f"- البوابة مرتبطة: gate_cert_sha256={gate_sha[:32]}…\n\n"
            "| # | القسم | البرهان |\n|---|---|---|\n"
        )
        for i, key in enumerate(order):
            s = secs.get(key, {})
            status_md += (f"| {labels[i]} | {key} | ok={s.get('ok')} · "
                          f"{json.dumps({k: v for k, v in s.items() if k != 'ok'}, ensure_ascii=False)[:120]} |\n")
        status_md += (
            "\n## التشغيل الحقيقي عن بُعد (للمشغّل)\n\n"
            "1. الواجهة: انشر `remote/web` على GitHub Pages (workflow جاهز)\n"
            "   أو افتحها من الجهاز نفسه عبر البوابة مباشرة.\n"
            "2. البوابة: `NEXUS.exe --remote` (headless) أو زر الإعدادات في الواجهة.\n"
            "3. النفق: `cloudflared tunnel --url http://127.0.0.1:8899` → ضع الرابط\n"
            "   والتوكن (`remote\\token.txt`) في هاتفك (صف الاقتران).\n"
        )
        (HERE / "PHASE-28-STATUS.md").write_text(status_md, encoding="utf-8")

        readme = (
            "# NEXUS Remote — دليل النشر (PHASE 28)\n\n"
            "## الواجهة على GitHub Pages (28.1)\n"
            "- الملفات: `remote/web/index.html + app.css + app.js` — ثابتة بالكامل\n"
            "  (بدون build)، مسارات نسبية، جاهزة للنشر كما هي.\n"
            "- الـworkflow: `.github/workflows/pages.yml` ينشر `remote/web`\n"
            "  تلقائياً عند أي push يلمسها.\n"
            "- في الهاتف: أدخل رابط Pages في صف الاقتران + التوكن.\n\n"
            "## البوابة (28.2)\n"
            "- `NEXUS.exe --remote` → تخدم الواجهة + الـAPI على 127.0.0.1:8899\n"
            "- التوكن: `M:\\NEXUS\\remote\\token.txt` (يولَّد تلقائياً)\n"
            "- النفق العام: `cloudflared tunnel --url http://127.0.0.1:8899`\n\n"
            "## الـAPI\n"
            "| المسار | الوصف | توثيق |\n"
            "|---|---|---|\n"
            "| GET /api/health | فحص حي (بدون توكن) | 28.0 |\n"
            "| GET /api/status | حالة النظام | توكن |\n"
            "| GET /api/tasks | مهام المستودع الحقيقية | توكن |\n"
            "| POST /api/commands | chat/task/pause/resume/checkpoint | توكن |\n"
            "| GET /api/commands[/id] | حالة الأوامر | توكن |\n"
            "| POST /api/files/push | هاتف→جهاز (b64، حتى 8MB) | توكن |\n"
            "| GET /api/files · /get?name= | outbox→هاتف | توكن |\n\n"
            "الأمان: Bearer token على كل شيء عدا health · رفض مسارات\n"
            "العبور (traversal) مُختبَر كتحقق فعلي في الشهادة.\n"
        )
        (NEXUS / "remote" / "README-DEPLOY.md").write_text(readme, encoding="utf-8")

        card = (
            "# بطاقة المشروع — NEXUS Project Card (PHASE 28)\n"
            "- **المنتج**: NEXUS Windows Product v0.1 — NEXUS.exe حقيقي يعمل على جهاز Windows الحقيقي\n"
            "- **النواة**: v0.25.0 · 28 حزمة نواة · 37 وحدة تستورد بنجاح في كل إقلاع\n"
            "- **بوابة MIDPOINT**: 10/10 ✅ — شهادة موقعة `proofs\\midpoint_gate.json`\n"
            f"  (gate_cert_sha256={gate_sha[:32]}…)\n"
            "- **PHASE 26**: Desktop UI Production — 26.1–26.11 PASS · "
            f"`proofs\\phase26_ui.json` ({p26_sha[:20]}…)\n"
            "- **PHASE 27**: Tray + Startup Production — 27.1–27.8 PASS · "
            f"`proofs\\phase27_ui.json` ({p27_sha[:20]}…)\n"
            "- **PHASE 28**: Remote Web — الواجهة الثابتة + البوابة + الأوامر عن بُعد "
            f"+ نقل ملفات مُوثَّق · `proofs\\phase28_remote.json` ({p28_sha[:20]}…) · "
            f"port={cert.get('port')} · traversal مرفوض كتحقق\n"
            "- **القدرات (MIDPOINT-10)**: Full Stack · Android · Research · Coding · "
            "Automation · Computer · Documents\n"
            "- **الجهاز**: i7-3770 (AVX بلا AVX2) · Ollama MODE A2 · GTX 750 Ti 4GB\n"
            "- **القوانين**: local-first · stdlib core · evidence or silence · القرص يحكم\n"
            f"- **التاريخ**: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"- **exe**: dist\\NEXUS.exe — {DIST_EXE.stat().st_size} B · sha256 {exe_sha}\n"
            "- **اللقطات**: `proofs\\phase26\\sec_01..11` · `proofs\\phase27\\sec_02..06`\n"
            "- **شهادات**: phase26 (PASS) · phase27 (PASS) · phase28 (PASS) · cards (PASS)\n"
        )
        (PROOFS / "PROJECT-CARD.md").write_text(card, encoding="utf-8")
        result["stages"]["certify"] = {
            "status_md": str(HERE / "PHASE-28-STATUS.md"),
            "readme": str(NEXUS / "remote" / "README-DEPLOY.md"),
            "project_card": str(PROOFS / "PROJECT-CARD.md"),
            "phase28_cert_sha256": p28_sha}

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
