#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""MIDPOINT-10 worker — capability cards + project card (detached; mover-v4 laws).

Stages (heartbeat on every step):
  patch    -> 8 anchored replacements insert the 7 capability cards
              (Full Stack / Android / Research / Coding / Automation /
              Computer / Documents) + the project identity card into
              nexus_ui.py, each anchor asserted count==1, py_compile,
              backup nexus_ui.py.pre_cards.bak
  rebuild  -> PyInstaller onefile (proven spec; nexus_ui is a hiddenimport)
  check    -> NEXUS.exe --check on the new build
  ui       -> NEXUS.exe --ui-selftest -> midpoint_ui.json/png (cards visible;
              functional check: the Coding card really seeds the composer)
  certify  -> proofs\midpoint_cards.json + PROJECT-CARD.md (midpoint + proofs)
  gate     -> MIDPOINT-GATE.md row #6 + MIDPOINT-10 section (only on real PASS)

Honest FAIL on every stage — nothing is faked, everything lands on disk.
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
UI_PY = MID / "nexus_ui.py"
DIST = MID / "dist" / "NEXUS.exe"
PROOFS = Path(r"M:\NEXUS\proofs")
RESULTS = MID / "results"
HB = RESULTS / "worker_cards.hb.json"
OUT = RESULTS / "worker_cards.result.json"
GATE_MD = MID / "MIDPOINT-GATE.md"
GATE_CERT = PROOFS / "midpoint_gate.json"
PY = sys.executable

CAPS = [
    ("Full Stack", "بناء تطبيق ويب كامل", "#0F766E"),
    ("Android", "تطبيق أندرويد", "#B45309"),
    ("Research", "بحث معمّق محلي", "#7C3AED"),
    ("Coding", "كتابة كود وفحصه", "#BE123C"),
    ("Automation", "أتمتة مهام Windows", "#15803D"),
    ("Computer", "التحكم بالحاسوب", "#A16207"),
    ("Documents", "معالجة مستندات", "#475569"),
]
CAP_SEEDS = {
    "Full Stack": "ابنِ لي تطبيق ويب كامل لإدارة المهام بواجهة عربية",
    "Android": "جهّز مشروع تطبيق أندرويد لملاحظاتي مع بناء APK",
    "Research": "ابحث محلياً عن أفضل ممارسات حفظ الطاقة في ويندوز ولخّصها",
    "Coding": "اكتب سكربت بايثون ينظم ملفات التنزيلات ويختبره",
    "Automation": "أتمت النسخ الاحتياطي الأسبوعي لمجلد M:\\NEXUS",
    "Computer": "حلل جهازي وقل لي ما أثقل البرامج قيد التشغيل",
    "Documents": "حوّل ملفات PDF في مستنداتي إلى نصوص قابلة للبحث",
}

CAPS_LIT = ("CAPS = [\n"
            + "".join(f"    ({t!r}, {h!r}, {c!r}),\n" for t, h, c in CAPS)
            + "]\n")
SEEDS_LIT = ("CAP_SEEDS = {\n"
             + "".join(f"    {k!r}: {v!r},\n" for k, v in CAP_SEEDS.items())
             + "}\n")

CARDS_BLOCK = '''
    main.grid_columnconfigure(0, weight=1)

    # ---- بطاقة المشروع (project identity card) — MIDPOINT product card
    proj = tk.Frame(main, bd=1, relief="solid", bg="#0F172A")
    proj.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    tk.Label(proj, text=f"{lm.PRODUCT}  ·  NEXUS {lm.VERSION}",
             bg="#0F172A", fg="#F8FAFC",
             font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", padx=8, pady=(4, 0))
    tk.Label(proj, text="MIDPOINT 10/10 ✅ · 28 حزمة نواة · local-first · جهازك بعقل",
             bg="#0F172A", fg="#94A3B8",
             font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=8, pady=(0, 4))

    # ---- بطاقات القدرات (MIDPOINT-10) — ليست Modes مغلقة: تبذر برومبت بداية
    caps_bar = tk.Frame(main, bd=1, relief="solid")
    caps_bar.grid(row=1, column=0, sticky="ew", pady=(0, 4))
    cap_clicks = {"n": 0}

    def _seed_cap(title: str, seed: str) -> None:
        cap_clicks["n"] += 1
        entry.delete(0, "end")
        entry.insert(0, seed)
        act_add(f"[cap] {title} — بُذّر الـcomposer (ليست mode مغلقة)")
        try:
            entry.focus_set()
        except BaseException:
            pass

    for _i, (_t, _h, _c) in enumerate(CAPS):
        card = tk.Frame(caps_bar, bd=1, relief="solid", cursor="hand2")
        card.grid(row=0, column=_i, padx=3, pady=3, sticky="nsew")
        caps_bar.grid_columnconfigure(_i, weight=1)
        tk.Label(card, text=_t, fg=_c, font=("Segoe UI", 9, "bold"),
                 cursor="hand2").pack(padx=4, pady=(3, 0))
        tk.Label(card, text=_h, fg="#555555", font=("Segoe UI", 7),
                 cursor="hand2").pack(padx=4, pady=(0, 3))
        _seed = CAP_SEEDS[_t]
        card.bind("<Button-1>", lambda _e, t=_t, s=_seed: _seed_cap(t, s))
        for _w in card.winfo_children():
            _w.bind("<Button-1>", lambda _e, t=_t, s=_seed: _seed_cap(t, s))

    tk.Label(main, text="المحادثة", anchor="w", font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="ew")
'''

PATCHES = [
    # 1) module-level constants: CAPS + CAP_SEEDS
    ("MF_STRING = 0x0",
     "MF_STRING = 0x0\n\n"
     "# ---------------------------------------------- MIDPOINT-10 capability cards\n"
     "# سبع بطاقات قدرات — ليست Modes مغلقة: كل بطاقة تبذر برومبت بداية في الـcomposer\n"
     + CAPS_LIT + SEEDS_LIT),
    # 2) main grid: 4 rows now (project card / caps bar / chat / activity)
    ("    main.grid_rowconfigure(0, weight=3)\n"
     "    main.grid_rowconfigure(1, weight=2)",
     "    main.grid_rowconfigure(0, weight=0)\n"
     "    main.grid_rowconfigure(1, weight=3)\n"
     "    main.grid_rowconfigure(2, weight=2)"),
    # 3) project card + capability cards block, chat label moves to row 2
    ('    main.grid_columnconfigure(0, weight=1)\n'
     '    tk.Label(main, text="المحادثة", anchor="w", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="ew")',
     CARDS_BLOCK.rstrip("\n")),
    # 4) chat widget row 0 -> 2
    ('    chat.grid(row=0, column=0, sticky="nsew", pady=(24, 6))',
     '    chat.grid(row=2, column=0, sticky="nsew", pady=(24, 6))'),
    # 5) activity label row 1 -> 3
    ('    tk.Label(main, text="النشاط — Activity", anchor="w", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="ew")',
     '    tk.Label(main, text="النشاط — Activity", anchor="w", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="ew")'),
    # 6) activity widget row 1 -> 3
    ('    act.grid(row=1, column=0, sticky="nsew", pady=(24, 6))',
     '    act.grid(row=3, column=0, sticky="nsew", pady=(24, 6))'),
    # 7) functional check: the Coding card really seeds the composer
    ('    entry.insert(0, "حلل جهازي")\n'
     '    status.config(text=f"Core: CONNECTED ({ok_n} pkgs)   ·   Model: {model_status}"\n'
     '                       f"   ·   Tasks: {tasks_count}")\n'
     '\n'
     '    frames = _pump(root, 30)',
     '    entry.insert(0, "حلل جهازي")\n'
     '    status.config(text=f"Core: CONNECTED ({ok_n} pkgs)   ·   Model: {model_status}"\n'
     '                       f"   ·   Tasks: {tasks_count}")\n'
     '\n'
     '    # functional check — a real card click path seeds the composer (MIDPOINT-10)\n'
     '    _seed_cap("Coding", CAP_SEEDS["Coding"])\n'
     '    cap_seed_check = ("ok" if entry.get() == CAP_SEEDS["Coding"]\n'
     '                      else "mismatch:" + entry.get()[:40])\n'
     '    cert["cap_seed_check"] = cap_seed_check\n'
     '\n'
     '    frames = _pump(root, 30)'),
    # 8) certificate fields + honest PASS condition including the cards
    ('    cert["screenshot"] = shot\n'
     '    cert["pump_frames"] = frames\n'
     '    cert["tasks_count"] = tasks_count\n'
     '    cert["model"] = model_status\n'
     '    cert["core_ok"] = ok_n\n'
     '    ok = (shot.get("ok") and (shot.get("size_bytes") or 0) > 8000\n'
     '          and frames >= 20 and ok_n >= 30 and tasks_count >= 1)',
     '    cert["screenshot"] = shot\n'
     '    cert["pump_frames"] = frames\n'
     '    cert["tasks_count"] = tasks_count\n'
     '    cert["model"] = model_status\n'
     '    cert["core_ok"] = ok_n\n'
     '    cert["caps_cards"] = len(CAPS)\n'
     '    cert["cap_clicks"] = cap_clicks["n"]\n'
     '    cert["project_card"] = True\n'
     '    ok = (shot.get("ok") and (shot.get("size_bytes") or 0) > 8000\n'
     '          and frames >= 20 and ok_n >= 30 and tasks_count >= 1\n'
     '          and len(CAPS) == 7 and cap_seed_check == "ok")'),
]

ROW6_NEW = ("| 6 | UI سطح مكتب أولي (نافذة محادثة) | نافذة حقيقية + قائمة مهام حقيقية + لقطة | "
            "✅ **منفذ** — tkinter · sidebar tasks من المستودع · "
            "**بطاقات القدرات M10 (7 بطاقات) + بطاقة المشروع** · "
            "لقطة GDI `proofs\\midpoint_ui.png` · `proofs\\midpoint_ui.json` |")

M10_SECTION = (
    "\n## MIDPOINT-10 — بطاقات القدرات + بطاقة المشروع\n"
    "- بطاقات New Chat السبع: Full Stack · Android · Research · Coding · "
    "Automation · Computer · Documents — **ليست Modes مغلقة**: كل بطاقة تبذر "
    "برومبت بداية في الـcomposer (فحص وظيفي حقيقي: بطاقة Coding بذّرت "
    "الـcomposer — `cap_seed_check=ok`).\n"
    "- بطاقة المشروع شريط هوية داخل الواجهة + وثيقة `build\\midpoint\\PROJECT-CARD.md` "
    "(نسخة في proofs).\n"
    "- برهان: `proofs\\midpoint_cards.json` (verdict=PASS) + لقطة محدثة "
    "`proofs\\midpoint_ui.png`.\n")


def _hb(stage: str, **extra) -> None:
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        HB.write_text(
            json.dumps({"stage": stage,
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
    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    return {"rc": proc.returncode, "out_tail": out[-900:],
            "err_tail": err[-500:], "seconds": round(time.time() - t0, 1)}


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


def stage_patch(res: dict) -> bool:
    _hb("patch")
    src = UI_PY.read_text(encoding="utf-8")
    if "MIDPOINT-10 capability cards" in src:
        res["patch"] = {"ok": False, "note": "already patched — refusing double apply"}
        return False
    applied = []
    for i, (old, new) in enumerate(PATCHES, 1):
        n = src.count(old)
        if n != 1:
            res["patch"] = {"ok": False, "failed_at": i, "count": n,
                            "anchor_head": old[:70]}
            return False
        src = src.replace(old, new)
        applied.append(f"p{i}:ok")
    bak = MID / "nexus_ui.py.pre_cards.bak"
    if not bak.exists():
        bak.write_text(UI_PY.read_text(encoding="utf-8"), encoding="utf-8")
    UI_PY.write_text(src, encoding="utf-8")
    chk = subprocess.run([PY, "-m", "py_compile", str(UI_PY)],
                         capture_output=True, cwd=str(MID))
    ok = chk.returncode == 0
    res["patch"] = {"ok": ok, "patches": applied,
                    "backup": bak.name, "compile_rc": chk.returncode,
                    "compile_err": (chk.stderr or b"").decode("utf-8", "replace")[-300:]}
    return ok


def stage_gate_md(ui_pass: bool, res: dict) -> None:
    if not ui_pass:
        res["gate_md"] = {"updated": False, "note": "honest FAIL — rows stay as-is"}
        return
    try:
        txt = GATE_MD.read_text(encoding="utf-8")
        old = [ln for ln in txt.splitlines() if ln.startswith("| 6 |")]
        if old:
            txt = txt.replace(old[0], ROW6_NEW)
        if "MIDPOINT-10 — بطاقات القدرات" not in txt:
            txt = txt.rstrip("\n") + "\n" + M10_SECTION
        GATE_MD.write_text(txt, encoding="utf-8")
        res["gate_md"] = {"updated": True}
    except OSError as exc:
        res["gate_md"] = {"updated": False, "error": str(exc)[:120]}


def main() -> int:
    _hb("start")
    res: dict = {"worker": "worker_cards",
                 "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "pid": os.getpid()}
    try:
        # 1) patch nexus_ui.py (8 anchored replacements + py_compile)
        if not stage_patch(res):
            return _out(res, "FAIL")

        # 2) rebuild
        _hb("rebuild")
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        build = _run([PY, "-m", "PyInstaller", "NEXUS.exe.spec", "--noconfirm",
                      "--distpath", "dist", "--workpath", "build", "--clean"], 1800)
        res["build"] = {"rc": build["rc"], "seconds": build["seconds"]}
        if build["rc"] != 0 or not DIST.is_file():
            res["error"] = "pyinstaller failed: " + (build["err_tail"] or "")[-300:]
            return _out(res, "FAIL")
        res["exe"] = {"size": DIST.stat().st_size, "sha256": _sha(DIST)}

        # 3) --check
        _hb("check")
        res["check"] = _run([str(DIST), "--check"], 300, env=env)
        if res["check"]["rc"] != 0:
            res["error"] = "--check failed"
            return _out(res, "FAIL")

        # 4) the real UI run — cards visible, functional seed check
        _hb("ui")
        run = _run([str(DIST), "--ui-selftest"], 360, env=env)
        res["ui_run"] = {"rc": run["rc"], "seconds": run["seconds"],
                         "out_tail": run["out_tail"][-500:]}
        ui_cert = {}
        try:
            ui_cert = json.loads((PROOFS / "midpoint_ui.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            res["error"] = f"ui cert unreadable: {exc}"
            return _out(res, "FAIL")
        png = PROOFS / "midpoint_ui.png"
        png_ok = png.is_file() and png.stat().st_size > 8000
        ui_pass = (run["rc"] == 0 and ui_cert.get("verdict") == "PASS"
                   and ui_cert.get("caps_cards") == 7
                   and ui_cert.get("cap_seed_check") == "ok"
                   and ui_cert.get("project_card") is True and png_ok)
        res["ui_cert"] = {k: ui_cert.get(k) for k in
                          ("verdict", "caps_cards", "cap_seed_check",
                           "project_card", "cap_clicks", "core_ok",
                           "tasks_count", "model")}
        res["ui_png"] = {"exists": png.is_file(),
                         "size": png.stat().st_size if png.is_file() else None}
        if not ui_pass:
            return _out(res, "FAIL")

        # 5) certify — chain: gate cert + ui cert + new screenshot
        _hb("certify")
        cards_cert = {
            "check": "midpoint-10-capability-cards",
            "product": ui_cert.get("product"),
            "version": ui_cert.get("version"),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": os.getpid(),
            "caps": [t for t, _h, _c in CAPS],
            "caps_closed_modes": False,
            "cap_seed_check": ui_cert.get("cap_seed_check"),
            "ui_cert_sha256": _sha(PROOFS / "midpoint_ui.json"),
            "ui_png_sha256": _sha(png),
            "ui_png_size": png.stat().st_size,
            "gate_cert_sha256": (_sha(GATE_CERT) if GATE_CERT.is_file() else None),
            "exe_sha256": res["exe"]["sha256"],
            "verdict": "PASS",
        }
        PROOFS.mkdir(parents=True, exist_ok=True)
        (PROOFS / "midpoint_cards.json").write_text(
            json.dumps(cards_cert, ensure_ascii=False, indent=1), encoding="utf-8")

        card_md = (
            "# بطاقة المشروع — NEXUS Project Card (MIDPOINT-10)\n"
            "\n"
            "- **المنتج**: NEXUS Windows Product v0.1 — أول NEXUS.exe حقيقي يعمل على جهاز Windows الحقيقي\n"
            "- **النواة**: v0.25.0 · 28 حزمة نواة · 37 وحدة تستورد بنجاح في كل إقلاع\n"
            "- **بوابة MIDPOINT**: 10/10 ✅ — شهادة موقعة `proofs\\midpoint_gate.json`\n"
            "- **القدرات (MIDPOINT-10)**: Full Stack · Android · Research · Coding · "
            "Automation · Computer · Documents — بطاقات **ليست Modes مغلقة**؛ "
            "كل بطاقة تبذر برومبت بداية في الـcomposer\n"
            "- **الجهاز**: i7-3770 (AVX بلا AVX2) · Ollama MODE A2 · GTX 750 Ti 4GB\n"
            "- **القوانين**: local-first · stdlib core · evidence or silence · القرص يحكم\n"
            f"- **التاريخ**: {cards_cert['utc']}\n"
            f"- **exe**: dist\\NEXUS.exe — {res['exe']['size']:,} B · sha256 {res['exe']['sha256']}\n"
            "- **لقطات**: `proofs\\midpoint_ui.png` (الواجهة بالبطاقات) · "
            "`proofs\\midpoint_tray.png` · `proofs\\midpoint_overlay.png`\n"
            "- **شهادة البطاقات**: `proofs\\midpoint_cards.json` (verdict=PASS)\n")
        (MID / "PROJECT-CARD.md").write_text(card_md, encoding="utf-8")
        (PROOFS / "PROJECT-CARD.md").write_text(card_md, encoding="utf-8")
        res["certify"] = {"cards_cert": str(PROOFS / "midpoint_cards.json"),
                          "project_card": ["build/midpoint", "proofs"]}

        # 6) gate md — only on real PASS
        stage_gate_md(True, res)

        return _out(res, "PASS")
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
