"""Detached MIDPOINT gate #4 worker v5 — clean re-certification of the chat.

exe v3 (sha256 455c31ca...) already has the Ollama MODE A2 adapter and is
built. Attempt 3's transcript PROVES the chat worked end-to-end (ollama
online, real qwen3:0.6b Arabic reply) — the cert said FAIL only because
the worker's reply parser required the line to START with 'nexus>' while
the real reply shares its first line with the 'you>' prompt and spans
multiple lines. That parser bug is mine, outside the product.

v5 fixes:
    1. reply extraction: first 'nexus>' up to the next 'you>' (multi-line)
    2. PYTHONIOENCODING=utf-8 for the exe so Arabic survives the pipe
    3. ollama lifecycle (serve or reuse live 11434) + model presence
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent           # M:\\NEXUS\\build\\midpoint
PROOFS = HERE.parent.parent / "proofs"
RESULTS = HERE / "results"
EXE = HERE / "dist" / "NEXUS.exe"
LOG = RESULTS / "gate5.phases.log"
OLLAMA_LOG = RESULTS / "ollama.log"
TRANSCRIPT = RESULTS / "chat_transcript.txt"
CERT = PROOFS / "midpoint_chat.json"

OLLAMA = Path(r"C:\Users\MohandsMohammad\AppData\Local\Programs\Ollama\ollama.exe")
MODEL_NAME = "qwen3:0.6b"          # already pulled on this machine (58s, 18:01Z)
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


def port_open(port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def extract_reply(raw: str) -> str:
    """First 'nexus>' up to the next 'you>' — multi-line safe."""
    idx = raw.find("nexus>")
    if idx < 0:
        return ""
    seg = raw[idx + len("nexus>"):]
    end = seg.find("you>")
    if end >= 0:
        seg = seg[:end]
    return seg.strip()


def main() -> int:
    t0 = time.time()
    cert: dict = {
        "product": "NEXUS first real chat (MIDPOINT #4, Ollama MODE A2)",
        "utc": _utc(), "pid": os.getpid(), "prompt": PROMPT,
        "model": MODEL_NAME, "exe_sha256_prefix": "455c31ca",
        "system_proxies": urllib.request.getproxies(),
    }
    server: subprocess.Popen | None = None
    reused = False
    try:
        hb("worker_gate5_start", f"pid={os.getpid()}")
        if not EXE.exists():
            cert["verdict"] = "FAIL"
            cert["error"] = "dist\\NEXUS.exe missing"
            return _finish(cert, t0)
        if not OLLAMA.exists():
            cert["verdict"] = "FAIL"
            cert["error"] = "ollama.exe not found"
            return _finish(cert, t0)

        reused = port_open(11434, 1.5)
        cert["ollama_server"] = "reused_live_11434" if reused else "spawned"
        if not reused:
            hb("ollama_serve_begin")
            with open(OLLAMA_LOG, "ab") as fh:
                server = subprocess.Popen(
                    [str(OLLAMA), "serve"], stdout=fh, stderr=fh,
                    stdin=subprocess.DEVNULL, cwd=str(HERE))
            time.sleep(4)
            if server.poll() is not None:
                cert["verdict"] = "FAIL"
                cert["error"] = f"ollama serve died rc={server.returncode}"
                hb("ollama_died", f"rc={server.returncode}")
                return _finish(cert, t0)
            deadline = time.time() + 90
            while time.time() < deadline and not port_open(11434, 1.5):
                time.sleep(3)
            if not port_open(11434, 1.5):
                cert["verdict"] = "FAIL"
                cert["error"] = "11434 never opened"
                return _finish(cert, t0)
        hb("ollama_up", cert["ollama_server"])

        lst = subprocess.run([str(OLLAMA), "list"], capture_output=True,
                             text=True, timeout=120)
        cert["ollama_list"] = (lst.stdout or "")[:400]
        if MODEL_NAME not in (lst.stdout or ""):
            hb("model_missing_pull_again")
            p = subprocess.run([str(OLLAMA), "pull", MODEL_NAME],
                               capture_output=True, text=True, timeout=1200)
            if p.returncode != 0:
                cert["verdict"] = "FAIL"
                cert["error"] = f"pull {MODEL_NAME} failed (honest)"
                return _finish(cert, t0)
        hb("model_ready", MODEL_NAME)

        hb("chat_begin", f"NEXUS.exe --chat --ollama-model {MODEL_NAME}")
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"       # Arabic survives the pipe
        p = subprocess.Popen(
            [str(EXE), "--chat", "--ollama-model", MODEL_NAME],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", cwd=str(HERE), env=env)
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
        cert["transcript_excerpt"] = (out or "")[:600]
        reply = extract_reply(out or "")
        cert["reply"] = reply[:800]
        cert["verdict"] = "PASS" if reply else "FAIL"
        if not reply:
            cert["error"] = "no 'nexus>' segment found (honest)"
        hb("chat_done", f"reply_chars={len(reply)}")
        return _finish(cert, t0)
    except BaseException as exc:  # noqa: BLE001
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return _finish(cert, t0)
    finally:
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=15)
            except Exception:  # noqa: BLE001
                try:
                    server.kill()
                except Exception:  # noqa: BLE001
                    pass
            hb("ollama_stopped")


def _finish(cert: dict, t0: float) -> int:
    cert["chat_seconds"] = round(time.time() - t0, 2)
    cert["utc_end"] = _utc()
    try:
        PROOFS.mkdir(parents=True, exist_ok=True)
        CERT.write_text(json.dumps(cert, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError:
        pass
    hb("done", f"verdict={cert.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
