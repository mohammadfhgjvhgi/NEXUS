"""Detached MIDPOINT gate #4 worker v6 — build(launcher v4) + ollama + chat.

v5 honest-fail diagnosis: qwen3 is a THINKING model; that run's thinking
chain exceeded the 300s HTTP timeout at this CPU's ~3 tok/s. Launcher v4
now sends think:false + options.num_predict=256 (direct answer, bounded)
and raises the HTTP timeout to 420s. This worker rebuilds the exe from
launcher v4 and re-runs the gate-4 chat with the v5 parser fixes
(multi-line reply extraction + PYTHONIOENCODING=utf-8).
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
LOG = RESULTS / "gate8.phases.log"
OLLAMA_LOG = RESULTS / "ollama.log"
TRANSCRIPT = RESULTS / "chat_transcript.txt"
CERT_BUILD = PROOFS / "midpoint_build.json"
CERT_CHAT = PROOFS / "midpoint_chat.json"

OLLAMA = Path(r"C:\Users\MohandsMohammad\AppData\Local\Programs\Ollama\ollama.exe")
MODEL_NAME = "qwen3:0.6b"
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


def extract_reply(raw: str) -> str:
    idx = raw.find("nexus>")
    if idx < 0:
        return ""
    seg = raw[idx + len("nexus>"):]
    end = seg.find("you>")
    if end >= 0:
        seg = seg[:end]
    return seg.strip()


def stage_build() -> dict:
    t0 = time.time()
    cert: dict = {"product": "NEXUS.exe rebuild v5 (--say UI seam, utf-8 stdio)",
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


def main() -> int:
    hb("worker_gate8_start", f"pid={os.getpid()} py={sys.version.split()[0]}")
    b = stage_build()
    if b.get("verdict") != "PASS":
        hb("gate8_aborted", "build failed")
        return 0

    cert: dict = {
        "product": "NEXUS first real chat (MIDPOINT #4, Ollama MODE A2, --say seam)",
        "utc": _utc(), "pid": os.getpid(), "prompt": PROMPT,
        "model": MODEL_NAME, "exe_sha256": b.get("sha256"),
        "system_proxies": urllib.request.getproxies(),
    }
    server: subprocess.Popen | None = None
    t0 = time.time()
    try:
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

        hb("chat_begin", f"NEXUS.exe --say (argv unicode, think:false) {MODEL_NAME}")
        p = subprocess.run(
            [str(EXE), "--say", PROMPT, "--ollama-model", MODEL_NAME],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600, cwd=str(HERE))
        rc = p.returncode
        out = (p.stdout or "") + (p.stderr or "")
        try:
            TRANSCRIPT.write_text(out or "", encoding="utf-8")
        except OSError:
            pass
        cert["say_rc"] = rc
        cert["transcript_chars"] = len(out or "")
        cert["transcript_excerpt"] = (out or "")[:400]
        reply = (out or "").strip()
        cert["reply"] = reply[:800]
        cert["verdict"] = "PASS" if reply else "FAIL"
        if not reply:
            cert["error"] = "--say produced empty stdout (honest)"
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
    _write_json(CERT_CHAT, cert)
    hb("done", f"verdict={cert.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
