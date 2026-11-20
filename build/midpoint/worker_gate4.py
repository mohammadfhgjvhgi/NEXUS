"""Detached MIDPOINT gate #4 worker v3 — build + Ollama + first real chat.

Hardware truth (device_runtime_recon.json): i7-3770 (Ivy Bridge — AVX,
NOT AVX2) → every LM Studio llama.cpp backend dies 0xC000007D instantly.
BUT Ollama is installed on this machine, and GTX 750 Ti 4GB is live.

Plan (one trigger, all evidence on disk):
    BUILD  : rebuild NEXUS.exe from the v3 launcher (no-proxy + MODE A2
             Ollama adapter) — PyInstaller onefile, sha256, --check
    OLLAMA : start `ollama serve` (or reuse a live 11434) → import the
             LOCAL GGUF from the .mimo_storage junction as qwen3-mini
             (`ollama create` — ZERO downloads) → fallback: ollama pull
    CHAT   : run the real NEXUS.exe --chat --ollama-model qwen3-mini with
             a scripted Arabic prompt → transcript → honest certificate

Evidence:
    results\\gate4.phases.log          all heartbeats
    results\\ollama.log                ollama serve stdout/stderr
    results\\chat_transcript.txt       full --chat transcript
    proofs\\midpoint_build.json        build verdict (new exe sha256)
    proofs\\midpoint_chat.json         gate #4 verdict + prompt + reply
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent           # M:\\NEXUS\\build\\midpoint
NEXUS_ROOT = HERE.parent.parent                  # M:\\NEXUS
PROOFS = NEXUS_ROOT / "proofs"
RESULTS = HERE / "results"
EXE = HERE / "dist" / "NEXUS.exe"
LOG = RESULTS / "gate4.phases.log"
OLLAMA_LOG = RESULTS / "ollama.log"
TRANSCRIPT = RESULTS / "chat_transcript.txt"
CERT_BUILD = PROOFS / "midpoint_build.json"
CERT_CHAT = PROOFS / "midpoint_chat.json"

OLLAMA = Path(r"C:\Users\MohandsMohammad\AppData\Local\Programs\Ollama\ollama.exe")
GGUF = Path(r"C:\Users\MohandsMohammad\.mimo_storage\snapshots\snap_000001_qwen3-0.6b-q4km.gguf")
MODEL_NAME = "qwen3-mini"
PROMPT = "مرحبًا يا NEXUS، عرّف عن نفسك بجملة واحدة."


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hb(phase: str, detail: str = "") -> None:
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": _utc(), "phase": phase,
                                 "detail": str(detail)[:240]},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass


def _write_json(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError:
        pass


def port_open(port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------ stage: BUILD

def stage_build() -> dict:
    t0 = time.time()
    cert: dict = {"product": "NEXUS.exe rebuild v3 (MODE A2 ollama adapter)",
                  "utc": _utc(), "pid": os.getpid(),
                  "python": sys.version.split()[0]}
    try:
        py = sys.executable
        hb("build_begin")
        b = subprocess.run([py, "-m", "PyInstaller", "--noconfirm", "--clean",
                            "NEXUS.exe.spec"], cwd=str(HERE),
                           capture_output=True, text=True, timeout=2400)
        cert["build_rc"] = b.returncode
        if b.returncode != 0 or not EXE.exists():
            cert["verdict"] = "FAIL"
            cert["error"] = "pyinstaller failed or exe missing (honest)"
            cert["tail"] = ((b.stderr or "") + (b.stdout or ""))[-900:]
            return cert
        cert["exe_size_bytes"] = EXE.stat().st_size
        cert["sha256"] = sha256_of(EXE)
        hb("build_done", f"size={cert['exe_size_bytes']} sha256={cert['sha256'][:16]}...")
        r = subprocess.run([str(EXE), "--check"], cwd=str(HERE),
                           capture_output=True, text=True, timeout=300)
        cert["check_rc"] = r.returncode
        cert["check_verdict"] = "PASS" if r.returncode == 0 else "FAIL"
        cert["verdict"] = cert["check_verdict"]
        hb("exe_check_done", f"rc={r.returncode}")
        return cert
    except BaseException as exc:  # noqa: BLE001
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return cert
    finally:
        cert["build_seconds"] = round(time.time() - t0, 2)
        cert["utc_end"] = _utc()
        _write_json(CERT_BUILD, cert)
        hb("build_stage_done", f"verdict={cert.get('verdict')}")


# ----------------------------------------------------------- stage: OLLAMA

def stage_ollama(cert: dict) -> dict:
    """Start/reuse Ollama and guarantee MODEL_NAME exists. Honest fails."""
    if not OLLAMA.exists():
        cert["verdict"] = "FAIL"
        cert["error"] = "ollama.exe not found on this machine"
        return cert
    if not GGUF.exists():
        cert["verdict"] = "FAIL"
        cert["error"] = f"local GGUF missing: {GGUF}"
        return cert

    reused = port_open(11434, 1.5)
    server: subprocess.Popen | None = None
    cert["ollama_server"] = "reused_live_11434" if reused else "spawned"
    try:
        if not reused:
            hb("ollama_serve_begin")
            with open(OLLAMA_LOG, "ab") as fh:
                server = subprocess.Popen(
                    [str(OLLAMA), "serve"], stdout=fh, stderr=fh,
                    stdin=subprocess.DEVNULL, cwd=str(HERE))
            time.sleep(4)
            if server.poll() is not None:
                cert["verdict"] = "FAIL"
                cert["error"] = f"ollama serve died instantly rc={server.returncode} (CPU caps?)"
                hb("ollama_died_instantly", f"rc={server.returncode}")
                return cert
            deadline = time.time() + 90
            while time.time() < deadline and not port_open(11434, 1.5):
                time.sleep(3)
            if not port_open(11434, 1.5):
                cert["verdict"] = "FAIL"
                cert["error"] = "ollama serve never opened 11434 in 90s"
                hb("ollama_no_port")
                return cert
        hb("ollama_up", cert["ollama_server"])

        out = subprocess.run([str(OLLAMA), "list"], capture_output=True,
                             text=True, timeout=120)
        listing = out.stdout or ""
        cert["ollama_list_before"] = listing[:500]
        hb("ollama_listed", listing.replace(chr(10), ' | ')[:200])

        model = MODEL_NAME
        if MODEL_NAME not in listing:
            hb("ollama_create_begin", f"import {GGUF.name} (zero downloads)")
            modelfile = RESULTS / "Modelfile.qwen3-mini"
            modelfile.write_text(
                f"FROM {GGUF}\nPARAMETER num_ctx 2048\n", encoding="utf-8")
            c = subprocess.run(
                [str(OLLAMA), "create", MODEL_NAME, "-f", str(modelfile)],
                capture_output=True, text=True, timeout=600)
            cert["ollama_create_rc"] = c.returncode
            cert["ollama_create_tail"] = ((c.stdout or "") + (c.stderr or ""))[-500:]
            if c.returncode != 0:
                hb("ollama_create_failed", cert["ollama_create_tail"][:180])
                model = "qwen3:0.6b"
                hb("ollama_pull_fallback", model)
                p = subprocess.run([str(OLLAMA), "pull", model],
                                   capture_output=True, text=True, timeout=1200)
                cert["ollama_pull_rc"] = p.returncode
                if p.returncode != 0:
                    cert["verdict"] = "FAIL"
                    cert["error"] = "both ollama create and pull failed (honest)"
                    cert["pull_tail"] = ((p.stdout or "") + (p.stderr or ""))[-500:]
                    return cert
            out2 = subprocess.run([str(OLLAMA), "list"], capture_output=True,
                                  text=True, timeout=120)
            cert["ollama_list_after"] = (out2.stdout or "")[:500]
            if model not in (out2.stdout or ""):
                cert["verdict"] = "FAIL"
                cert["error"] = f"model {model} still missing after import (honest)"
                return cert
        cert["model"] = model
        hb("ollama_model_ready", model)
        cert["_server"] = server
        return cert
    except BaseException as exc:  # noqa: BLE001
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return cert
    finally:
        cert["_reused"] = reused
        cert["_server"] = server


# ------------------------------------------------------------- stage: CHAT

def stage_chat(cert: dict, model: str) -> dict:
    t0 = time.time()
    try:
        hb("chat_begin", f"NEXUS.exe --chat --ollama-model {model}")
        p = subprocess.Popen(
            [str(EXE), "--chat", "--ollama-model", model],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", cwd=str(HERE))
        try:
            out, _ = p.communicate(input=PROMPT + "\nexit\n", timeout=600)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        try:
            TRANSCRIPT.write_text(out or "", encoding="utf-8")
        except OSError:
            pass
        cert["transcript_chars"] = len(out or "")
        reply = ""
        for line in (out or "").splitlines():
            ls = line.strip()
            if ls.startswith("nexus>") and len(ls) > 6:
                reply = ls[6:].strip()
        cert["prompt"] = PROMPT
        cert["reply"] = reply[:800]
        cert["verdict"] = "PASS" if reply else "FAIL"
        if not reply:
            cert["error"] = "no 'nexus>' reply line in transcript (honest)"
        hb("chat_done", f"reply_chars={len(reply)}")
        return cert
    except BaseException as exc:  # noqa: BLE001
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return cert
    finally:
        cert["chat_seconds"] = round(time.time() - t0, 2)
        cert["utc_end"] = _utc()
        _write_json(CERT_CHAT, cert)
        hb("chat_stage_done", f"verdict={cert.get('verdict')}")


def main() -> int:
    hb("worker_gate4_start", f"pid={os.getpid()} py={sys.version.split()[0]}")
    b = stage_build()
    if b.get("verdict") != "PASS":
        hb("gate4_aborted", "build failed")
        return 0
    cert: dict = {"product": "NEXUS first real chat (MIDPOINT #4, Ollama MODE A2)",
                  "utc": _utc(), "pid": os.getpid(),
                  "system_proxies": urllib.request.getproxies()}
    oc = stage_ollama(cert)
    server = oc.pop("_server", None)
    reused = oc.pop("_reused", False)
    if oc.get("verdict") == "FAIL" or "model" not in oc:
        oc["utc_end"] = _utc()
        _write_json(CERT_CHAT, oc)
        hb("chat_stage_done", "verdict=FAIL (ollama stage)")
        return 0
    cert.update({k: v for k, v in oc.items() if k != "verdict"})
    cc = stage_chat(cert, oc["model"])
    if server is not None and not reused:
        try:
            server.terminate()
            server.wait(timeout=15)
        except Exception:  # noqa: BLE001
            try:
                server.kill()
            except Exception:  # noqa: BLE001
                pass
        hb("ollama_stopped")
    hb("worker_gate4_done", f"chat verdict={cc.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
