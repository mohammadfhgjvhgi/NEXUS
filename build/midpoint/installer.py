# -*- coding: utf-8 -*-
"""NEXUS-Setup — Windows installer PREVIEW (MIDPOINT gate #9).

Production-path preview, honest about what it is: not the final polished
installer — it proves the REAL install path end to end on this machine:
    copy product  →  %LOCALAPPDATA%\\Programs\\NEXUS\\NEXUS.exe
    uninstall.bat →  real uninstaller script next to the product
    registry      →  HKCU Uninstall\\NEXUS entry (Arp-visible)
    Start Menu    →  Programs\\NEXUS\\NEXUS.bat (preview ships .bat;
                     the final installer ships a .lnk shortcut)
    launch + test →  the INSTALLED exe runs `--check` from its new home
Everything is recorded in proofs\\midpoint_install.json — PASS or the
exact error.
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


def _locate_root() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    for p in (base, *base.parents):
        if (p / "nexus" / "__init__.py").is_file():
            return p
    return Path(r"M:\NEXUS")


ROOT = _locate_root()
SRC = ROOT / "build" / "midpoint" / "dist" / "NEXUS.exe"
INST = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "NEXUS"
SM = (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows"
      / "Start Menu" / "Programs" / "NEXUS")
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NEXUS"


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    log: dict = {
        "product": "NEXUS Windows Product v0.1 — Setup preview",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "install_root": str(INST),
        "steps": [],
    }
    ok = True
    try:
        if not SRC.is_file():
            log["error"] = f"product not found: {SRC}"
            return _finish(log, False)

        # 1) copy the product into the install root
        INST.mkdir(parents=True, exist_ok=True)
        dst = INST / "NEXUS.exe"
        dst.write_bytes(SRC.read_bytes())
        log["steps"].append({
            "step": "copy", "from": str(SRC), "to": str(dst),
            "size": dst.stat().st_size, "sha256": _sha(dst),
            "src_sha256": _sha(SRC),
        })

        # 2) uninstall script
        un = INST / "uninstall.bat"
        un.write_text(
            "@echo off\r\n"
            f"del /f /q \"{dst}\"\r\n"
            f"rmdir /s /q \"{SM}\"\r\n"
            f"reg delete HKCU\\{UNINST_KEY} /f\r\n"
            f"rmdir /s /q \"{INST}\"\r\n",
            encoding="utf-8")
        log["steps"].append({"step": "uninstall-script", "path": str(un)})

        # 3) registry uninstall entry (HKCU — Arp-visible in Settings)
        entries = [
            ("DisplayName", "NEXUS — Windows Product v0.1"),
            ("DisplayVersion", "0.25.0-midpoint"),
            ("Publisher", "NEXUS local-first"),
            ("InstallLocation", str(INST)),
            ("DisplayIcon", str(dst)),
            ("UninstallString", str(un)),
            ("NoModify", 1), ("NoRepair", 1),
        ]
        for k, v in entries:
            kind = "REG_DWORD" if isinstance(v, int) else "REG_SZ"
            subprocess.run(
                ["reg", "add", f"HKCU\\{UNINST_KEY}", "/v", k, "/t", kind,
                 "/d", str(v), "/f"], capture_output=True)
        q = subprocess.run(
            ["reg", "query", f"HKCU\\{UNINST_KEY}", "/v", "DisplayName"],
            capture_output=True, text=True)
        log["steps"].append({
            "step": "registry", "query_rc": q.returncode,
            "out": (q.stdout or "")[:220],
        })
        ok = ok and q.returncode == 0

        # 4) Start Menu entry (preview ships a .bat; final ships .lnk)
        SM.mkdir(parents=True, exist_ok=True)
        (SM / "NEXUS.bat").write_text(
            "@echo off\r\nstart \"\" \"" + str(dst) + "\"\r\n",
            encoding="utf-8")
        log["steps"].append({"step": "start-menu", "path": str(SM / "NEXUS.bat")})

        # 5) launch + test the INSTALLED product from its new home
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        r = subprocess.run([str(dst), "--check"], capture_output=True,
                           timeout=300, env=env)
        out = (r.stdout or b"").decode("utf-8", "replace")
        log["steps"].append({
            "step": "installed-launch-test", "rc": r.returncode,
            "out_tail": out[-460:],
        })
        ok = ok and r.returncode == 0 and "verdict       : PASS" in out
    except BaseException:
        log["error"] = traceback.format_exc()[-900:]
        ok = False
    return _finish(log, ok)


def _finish(log: dict, ok: bool) -> int:
    log["verdict"] = "PASS" if ok else "FAIL"
    p = ROOT / "proofs" / "midpoint_install.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(log, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"certificate: {p}")
    except OSError as exc:
        print(f"[!] install certificate write failed (honest): {exc}")
    print(json.dumps({k: log.get(k) for k in ("verdict", "install_root")},
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
