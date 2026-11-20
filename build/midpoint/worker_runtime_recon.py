"""Detached runtime recon — WHY does every llama-server die instantly?

Every local llama.cpp backend died with 0xC000007D (illegal instruction)
or 0xC0000135 (DLL not found). This worker records the honest hardware
truth (CPU model, RAM, GPU) and finds EVERY local LLM runtime that already
exists on this machine (MiMo Edge first pool downloaded 26.8 GB of GGUFs
here — something must be able to run them).

Read-only recon. Evidence: proofs\\device_runtime_recon.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent           # M:\\NEXUS\\build\\midpoint
PROOFS = HERE.parent.parent / "proofs"
RESULTS = HERE / "results"
CERT = PROOFS / "device_runtime_recon.json"
LOG = RESULTS / "runtime_recon.phases.log"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hb(phase: str, detail: str = "") -> None:
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": _utc(), "phase": phase,
                                 "detail": str(detail)[:220]},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass


def ps_json(script: str) -> object:
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"{script} | ConvertTo-Json"],
            capture_output=True, text=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}
    if p.returncode != 0:
        return {"error": ((p.stderr or p.stdout or "")[:300] or f"rc={p.returncode}")}
    try:
        return json.loads(p.stdout)
    except Exception:  # noqa: BLE001
        return {"raw": (p.stdout or "")[:500]}


KEYWORDS = re.compile(
    r"mimo|ollama|jan|gpt4all|kobold|llama|msty|lm.?studio|anythingllm|"
    r"nvidia|openai|chatbox|lmstudio", re.I)

EXE_HINT = re.compile(
    r"ollama|llama|kobold|llamafile|mimo|jan|gpt4all|msty|server", re.I)


def scan_root(root: Path, depth: int = 1) -> list:
    hits: list = []
    try:
        for entry in root.iterdir():
            if KEYWORDS.search(entry.name):
                info = {"path": str(entry), "dir": entry.is_dir()}
                if entry.is_dir() and depth > 0:
                    try:
                        exes = [f.name for f in entry.glob("*.exe")
                                if EXE_HINT.search(f.name)][:12]
                        if exes:
                            info["exe_hits"] = exes
                    except OSError:
                        pass
                hits.append(info)
    except OSError:
        pass
    return hits


def main() -> int:
    t0 = time.time()
    cert: dict = {"product": "device runtime recon (why no llama-server runs)",
                  "utc": _utc(), "pid": os.getpid()}
    try:
        hb("start")
        cert["cpu"] = ps_json(
            "Get-CimInstance Win32_Processor | "
            "Select-Object Name, Caption, NumberOfCores, "
            "NumberOfLogicalProcessors, MaxClockSpeed")
        hb("cpu_done")
        cert["system"] = ps_json(
            "Get-CimInstance Win32_ComputerSystem | "
            "Select-Object Manufacturer, Model, TotalPhysicalMemory")
        cert["gpu"] = ps_json(
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name, AdapterRAM, DriverVersion")
        hb("hardware_done")

        where_hits = {}
        for name in ("ollama.exe", "llama-server.exe", "llama-cli.exe",
                     "koboldcpp.exe", "llamafile.exe", "mimo.exe"):
            try:
                p = subprocess.run(["where", name], capture_output=True,
                                   text=True, timeout=30)
                where_hits[name] = (p.stdout.strip().splitlines()
                                    if p.returncode == 0 else "not found")
            except Exception as exc:  # noqa: BLE001
                where_hits[name] = f"ERR {type(exc).__name__}"
        cert["where"] = where_hits
        hb("where_done")

        roots = [
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
            Path(r"C:\Users\MohandsMohammad\AppData\Local\Programs"),
            Path(r"C:\Users\MohandsMohammad\AppData\Local"),
        ]
        app_hits: dict = {}
        for r in roots:
            if r.exists():
                app_hits[str(r)] = scan_root(r, depth=1)
        cert["app_dir_hits"] = app_hits
        hb("apps_done", f"{sum(len(v) for v in app_hits.values())} hits")

        mimo = Path(r"C:\Users\MohandsMohammad\.mimo_storage")
        if mimo.exists():
            try:
                cert["mimo_storage_top"] = sorted(
                    e.name for e in mimo.iterdir())[:40]
            except OSError as exc:
                cert["mimo_storage_top"] = f"ERR {exc}"
        hb("mimo_done")
        return _finish(cert, t0)
    except BaseException as exc:  # noqa: BLE001
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return _finish(cert, t0)


def _finish(cert: dict, t0: float) -> int:
    cert["recon_seconds"] = round(time.time() - t0, 2)
    cert["utc_end"] = _utc()
    try:
        PROOFS.mkdir(parents=True, exist_ok=True)
        CERT.write_text(json.dumps(cert, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError:
        pass
    hb("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
