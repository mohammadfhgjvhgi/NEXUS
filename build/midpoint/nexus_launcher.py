"""NEXUS Launcher — MIDPOINT step #1 (product v0.1).

The first real NEXUS.exe seam: Launcher -> Core -> UI.

stdlib-only (Final Build Plan law). Modes:
    python nexus_launcher.py            boot + interactive banner
    python nexus_launcher.py --check    boot self-check only (GATE check #1);
                                        writes a boot certificate to proofs
    python nexus_launcher.py --chat     first real chat (llama-server MODE A
                                        adapter if the model runtime is up,
                                        honest offline message otherwise)
    python nexus_launcher.py --say "…"  one-shot chat from argv (UI seam)
    python nexus_launcher.py --task "…" first real task through the core's
                                        Task State Machine (GATE check #5)
    python nexus_launcher.py --ui-selftest / --tray-selftest /
                             --overlay-selftest   GATE #6/#7/#8 real windows

Never fakes anything: every probe records ok or the real error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
import time
import traceback
import urllib.request
from pathlib import Path

VERSION = "0.25.0"
PRODUCT = "NEXUS Windows Product v0.1 (MIDPOINT)"
HERE = Path(__file__).resolve().parent


def _locate_nexus_root() -> Path:
    """The launcher's first duty: locate the core — frozen-aware.

    Script mode : build/midpoint/nexus_launcher.py -> M:\\NEXUS (two up).
    Frozen mode : a onefile exe unpacks to a temp dir and __file__ lies,
                  so walk UP from the real exe location until a directory
                  holding nexus/__init__.py is found. Bundled imports win
                  anyway (FrozenImporter); the disk root is the honest
                  fallback so proofs still land on M:\\NEXUS.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = HERE
    for p in (base, *base.parents):
        if (p / "nexus" / "__init__.py").is_file():
            return p
    return HERE.parent.parent


NEXUS_ROOT = _locate_nexus_root()
if str(NEXUS_ROOT) not in sys.path:      # the launcher's first duty: locate the core
    sys.path.insert(0, str(NEXUS_ROOT))
PROOFS = NEXUS_ROOT / "proofs"
CERT = PROOFS / "midpoint_boot.json"
CERT_TASK = PROOFS / "midpoint_task.json"
LOCK = HERE / ".launcher.lock"

# the 28+ core packages (nexus/ on disk) — probe them ALL
CORE_MODULES = [
    "nexus.core.config", "nexus.events", "nexus.core.session",
    "nexus.core.engine", "nexus.core.persistence", "nexus.core.workspace",
    "nexus.core.scope", "nexus.core.policy", "nexus.resources",
    "nexus.models", "nexus.agents", "nexus.harness", "nexus.tools",
    "nexus.computer", "nexus.windows", "nexus.browser", "nexus.vision",
    "nexus.verification", "nexus.recovery", "nexus.health", "nexus.horizon",
    "nexus.orchestration", "nexus.security", "nexus.memory", "nexus.learning",
    "nexus.research", "nexus.documents", "nexus.speech", "nexus.codeintel",
    "nexus.coding", "nexus.git", "nexus.github", "nexus.remote",
    "nexus.skills", "nexus.plugins", "nexus.ui", "nexus.workspace",
]


def banner() -> None:
    print("=" * 58)
    print(f"  NEXUS {VERSION}  ·  {PRODUCT}")
    print("  Your computer. With a mind of its own.")
    print("  local-first  ·  stdlib core  ·  evidence or silence")
    print("=" * 58)


def acquire_lock() -> bool:
    """Single-instance guard, stale-safe (lock older than 24h is reclaimed)."""
    try:
        if LOCK.exists():
            age = time.time() - LOCK.stat().st_mtime
            if age < 24 * 3600:
                return False
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except OSError:
        return False


def release_lock() -> None:
    try:
        if LOCK.exists():
            LOCK.unlink()
    except OSError:
        pass


def probe_core() -> dict:
    probes: dict = {"ok": [], "err": {}}
    for mod in CORE_MODULES:
        try:
            importlib.import_module(mod)
            probes["ok"].append(mod)
        except BaseException as exc:  # noqa: BLE001
            probes["err"][mod] = f"{type(exc).__name__}: {exc}"[:160]
    return probes


def _local_opener() -> urllib.request.OpenerDirector:
    """Opener that NEVER proxies — a local-first product must talk to
    127.0.0.1 directly even when the machine has a system proxy set."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe_model_runtime(base: str = "http://127.0.0.1:8080") -> dict:
    """llama.cpp llama-server MODE A adapter seam (honest: up or down)."""
    try:
        with _local_opener().open(base + "/health", timeout=2) as r:
            body = (r.read() or b"{}")[:200]
        return {"up": True, "base": base, "health": body.decode("utf-8", "replace")}
    except BaseException as exc:  # noqa: BLE001
        return {"up": False, "base": base, "error": f"{type(exc).__name__}: {exc}"[:160]}


def probe_ollama(base: str = "http://127.0.0.1:11434") -> dict:
    """Ollama MODE A2 adapter seam (honest: up or down)."""
    try:
        with _local_opener().open(base + "/api/version", timeout=2) as r:
            body = (r.read() or b"{}")[:200]
        return {"up": True, "base": base, "version": body.decode("utf-8", "replace")}
    except BaseException as exc:  # noqa: BLE001
        return {"up": False, "base": base, "error": f"{type(exc).__name__}: {exc}"[:160]}


def boot_check() -> dict:
    t0 = time.time()
    cert: dict = {
        "product": PRODUCT, "version": VERSION,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": os.getpid(), "python": sys.version.split()[0],
    }
    try:
        import nexus  # noqa: F401  — the package root itself
        cert["package_root"] = "ok"
    except BaseException as exc:  # noqa: BLE001
        cert["package_root"] = f"ERR {type(exc).__name__}: {exc}"[:200]
    cert["core_probes"] = probe_core()
    ok_n = len(cert["core_probes"]["ok"])
    err_n = len(cert["core_probes"]["err"])
    cert["core_summary"] = {"ok": ok_n, "err": err_n}
    cert["model_runtime"] = probe_model_runtime()
    cert["boot_seconds"] = round(time.time() - t0, 2)
    cert["verdict"] = "PASS" if err_n == 0 and cert.get("package_root") == "ok" else "PARTIAL"
    return cert


def write_cert(cert: dict) -> None:
    try:
        PROOFS.mkdir(parents=True, exist_ok=True)
        CERT.write_text(json.dumps(cert, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as exc:
        print(f"[!] certificate write failed (honest): {exc}")


def pick_runtime(model_base: str):
    """The runtime ladder: llama-server MODE A on 8080, then Ollama MODE A2.
    Returns (engine, base) or (None, None) with honest prints."""
    rt = probe_model_runtime(model_base)
    if rt.get("up"):
        return "llama-server", rt["base"]
    ol = probe_ollama()
    if ol.get("up"):
        return "ollama", ol["base"]
    print("[x] no local model runtime — needs llama-server (8080) or Ollama (11434).")
    print(f"    llama-server: {rt.get('error')}")
    print(f"    ollama      : {ol.get('error')}")
    return None, None


def generate_once(engine: str, base: str, line: str, ollama_model: str) -> str:
    """One real generation through the chosen runtime. Returns the text."""
    if engine == "llama-server":
        payload = json.dumps({"prompt": line, "n_predict": 256}).encode("utf-8")
        req = urllib.request.Request(
            base + "/completion", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with _local_opener().open(req, timeout=120) as r:
            out = json.loads(r.read().decode("utf-8", "replace"))
        return (out.get("content") or out.get("response") or "").strip()
    payload = json.dumps(
        {"model": ollama_model, "prompt": line, "stream": False,
         "think": False, "options": {"num_predict": 256}}).encode("utf-8")
    req = urllib.request.Request(
        base + "/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    with _local_opener().open(req, timeout=420) as r:
        out = json.loads(r.read().decode("utf-8", "replace"))
    return (out.get("response") or "").strip()


def chat(model_base: str, ollama_model: str = "qwen3-mini") -> int:
    engine, base = pick_runtime(model_base)
    if engine is None:
        return 1
    print(f"[+] model runtime ONLINE: {engine} at {base} — first real chat.")
    print("    (type 'exit' to leave)")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line or line.lower() in ("exit", "quit"):
            return 0
        try:
            text = generate_once(engine, base, line, ollama_model)
            print("nexus>", text[:2000])
        except BaseException as exc:  # noqa: BLE001
            print(f"[x] model call failed (honest): {type(exc).__name__}: {exc}"[:200])
            return 1


def say(line: str, model_base: str, ollama_model: str = "qwen3-mini") -> int:
    """One-shot chat from argv (Unicode-safe on Windows) — the future UI
    seam: NEXUS.exe --say "..." prints ONLY the reply text."""
    engine, base = pick_runtime(model_base)
    if engine is None:
        return 1
    text = generate_once(engine, base, line, ollama_model)
    print(text)
    return 0


# --------------------------------------------------------------- GATE #5


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _transitions(task) -> list:
    return [
        {"from": str(t.from_state), "to": str(t.to_state), "reason": t.reason}
        for t in task.state_history
    ]


def run_task(goal: str, task_dir: str | None = None) -> int:
    """GATE #5 — first real task through the core's Task State Machine.

    Real boot → §2.3 hierarchy (User → Conversation → Task) → §2.4 engine
    transitions (validated, audited, evented) → §8.2 tool pipeline
    (discovery → permission → scope → resource → execute → normalize →
    verify) through the native filesystem tool → §2.5 persistence
    (atomic record + index, save → load roundtrip) → honest certificate.
    The policy/route configuration is the phase-7 exit-criteria one
    (registry + router over the real bus, no policy engine) — recorded
    here, never hidden.
    """
    from nexus.core.config.runtime import NexusRuntime
    from nexus.core.engine.states import TaskState
    from nexus.core.session.models import (
        StepStatus,
        TaskPlan,
        TaskResult,
        VerificationCheck,
        VerificationStatus,
    )
    from nexus.tools import build_tool_system

    t0 = time.time()
    cert: dict = {
        "product": PRODUCT, "version": VERSION,
        "check": "gate5-first-real-task",
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": os.getpid(), "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": str(sys.executable),
        "goal": goal,
    }

    def _finish(verdict: str, **extra) -> int:
        cert["verdict"] = verdict
        cert["seconds"] = round(time.time() - t0, 2)
        cert.update(extra)
        try:
            PROOFS.mkdir(parents=True, exist_ok=True)
            CERT_TASK.write_text(
                json.dumps(cert, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"certificate: {CERT_TASK}")
        except OSError as exc:
            print(f"[!] certificate write failed (honest): {exc}")
        print(json.dumps(
            {k: cert.get(k) for k in ("verdict", "task_id", "task_dir", "artifacts")},
            ensure_ascii=False))
        return 0 if verdict == "PASS" else 1

    try:
        runtime = NexusRuntime.boot(root=NEXUS_ROOT)
        cert["boot"] = {"root": str(NEXUS_ROOT)}
    except BaseException as exc:  # noqa: BLE001
        return _finish("FAIL", error=f"boot: {type(exc).__name__}: {exc}"[:300])

    ws = Path(task_dir) if task_dir else Path("M:/NEXUS-Test")
    cert["task_dir"] = str(ws)
    try:
        registry, router, _adapter, report = build_tool_system(
            workspace_root=ws, bus=runtime.bus,
            resources=runtime.resource_manager,
            confirm_danger_above=2, allow_network=False)
    except BaseException as exc:  # noqa: BLE001
        return _finish("FAIL", error=f"tools: {type(exc).__name__}: {exc}"[:300])
    cert["tools"] = {
        "native": list(report.get("native") or ()),
        "router": "phase7-exit-criteria configuration (no policy engine)",
    }

    sm = runtime.session_manager
    user = sm.create_user(display_name="Mohammad")
    conv = sm.create_conversation(user, title="أول مهمة حقيقية — MIDPOINT #5")
    task = sm.create_task(conv, goal=goal, prompt=goal)
    cert["task_id"] = task.id

    engine = runtime.engine
    folder_rel = "مهمة-أولى"
    file_rel = folder_rel + "/nexus_task_note.txt"
    note = (
        "هذا الملف كتبه NEXUS بنفسه — أول مهمة حقيقية عبر محرك المهام.\n"
        f"task_id: {task.id}\n"
        f"goal: {goal}\n"
        f"utc: {cert['utc']}\n"
        "engine: Task State Machine (13 state) · tool: filesystem عبر Router (7 مراحل)\n"
    )

    steps = [
        f"make_dirs: تحضير مجلد المهمة داخل {ws}",
        "write_text: كتابة ملف نصي عربي عبر أداة filesystem",
        "verify: التحقق من الأثر على القرص وإثباته في سجل التحقق",
    ]
    try:
        engine.start(task, reason="gate5 task started")            # CREATED → ANALYZING
        task.plan = TaskPlan.from_steps(steps)
        engine.transition(task, TaskState.PLANNING, reason="plan of 3 steps")
        engine.transition(task, TaskState.EXECUTING, reason="executing via filesystem tool")

        o_dir = router.route(
            "filesystem", {"op": "make_dirs", "path": folder_rel},
            task_id=task.id, agent_id="launcher")
        task.plan.steps[0].status = StepStatus.DONE if o_dir.ok else StepStatus.FAILED
        if not o_dir.ok:
            return _finish("FAIL", error=f"make_dirs: {o_dir.error}"[:300],
                           transitions=_transitions(task))
        o_txt = router.route(
            "filesystem",
            {"op": "write_text", "path": file_rel, "content": note},
            task_id=task.id, agent_id="launcher")
        task.plan.steps[1].status = StepStatus.DONE if o_txt.ok else StepStatus.FAILED
        if not o_txt.ok:
            return _finish("FAIL", error=f"write_text: {o_txt.error}"[:300],
                           transitions=_transitions(task))
        o_read = router.route(
            "filesystem", {"op": "read_text", "path": file_rel},
            task_id=task.id, agent_id="launcher")
    except BaseException as exc:  # noqa: BLE001
        return _finish("FAIL", error=f"engine/tool: {type(exc).__name__}: {exc}"[:300])

    # VERIFYING — evidence or silence
    engine.transition(task, TaskState.VERIFYING, reason="artifacts claimed on disk")
    folder = ws / folder_rel
    filep = ws / folder_rel / "nexus_task_note.txt"
    read_back = ""
    try:
        read_back = filep.read_text(encoding="utf-8") if filep.is_file() else ""
    except OSError as exc:
        read_back = f"<read error: {exc}>"
    checks = [
        ("folder_exists", folder.is_dir(), str(folder)),
        ("file_exists", filep.is_file(), str(filep)),
        ("content_roundtrip", read_back == note, f"{len(read_back)} chars read back"),
        ("router_ok_dir", o_dir.ok, f"{o_dir.elapsed_ms}ms"),
        ("router_ok_txt", o_txt.ok, f"{o_txt.elapsed_ms}ms"),
        ("router_readback", o_read.ok and task.id in o_read.output, "read_text via router"),
    ]
    task.verification.checks = [
        VerificationCheck(name=n, passed=bool(p), detail=str(d)[:160])
        for n, p, d in checks
    ]
    all_ok = all(p for _, p, _ in checks)
    task.verification.status = (VerificationStatus.PASSED if all_ok
                                else VerificationStatus.FAILED)
    if not all_ok:
        failed = [n for n, p, _ in checks if not p]
        return _finish("FAIL", error=f"verification failed: {failed}",
                       transitions=_transitions(task))

    engine.transition(task, TaskState.COMPLETED, reason="verification passed")
    task.result = TaskResult(
        summary="مجلد وملف نصي أُنشئا عبر محرك المهام وأداة filesystem — تحقق كامل",
        artifacts=[str(folder), str(filep)], success=True)
    for s in task.plan.steps:
        if s.status is StepStatus.PENDING:
            s.status = StepStatus.DONE

    # persistence — §2.5/§2.6: save → load → the task continues
    try:
        record_path = runtime.repository.save(task)
        reloaded = runtime.repository.load(task.id)
    except BaseException as exc:  # noqa: BLE001
        return _finish("FAIL", error=f"persistence: {type(exc).__name__}: {exc}"[:300],
                       transitions=_transitions(task))
    roundtrip = reloaded.id == task.id and str(reloaded.state) == str(task.state)
    task.verification.checks.append(VerificationCheck(
        name="persistence_roundtrip", passed=roundtrip,
        detail=f"{record_path.name} reloaded state={reloaded.state}"))
    if not roundtrip:
        return _finish("FAIL", error="persistence roundtrip mismatch",
                       transitions=_transitions(task))

    def _trace_of(o) -> dict:
        try:
            stages = [json.dumps(e, ensure_ascii=False)[:110]
                      for e in (o.trace.to_dict() if o.trace is not None else [])]
        except BaseException:  # noqa: BLE001
            stages = []
        ver = None
        try:
            ver = o.verification.to_dict() if o.verification is not None else None
        except BaseException:  # noqa: BLE001
            ver = None
        return {"tool": o.tool, "ok": o.ok, "elapsed_ms": o.elapsed_ms,
                "stages": stages, "verification": ver}

    return _finish(
        "PASS",
        task_id=task.id,
        transitions=_transitions(task),
        plan_steps=[{"d": s.description, "status": str(s.status)}
                    for s in task.plan.steps],
        artifacts={"folder": str(folder), "file": str(filep),
                   "record": str(record_path),
                   "record_sha256": _sha256_file(record_path)},
        tool_traces=[_trace_of(o) for o in (o_dir, o_txt, o_read)],
    )


def main(argv: list | None = None) -> int:
    # the product speaks UTF-8 no matter the console codepage (frozen-safe)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(prog="nexus_launcher")
    ap.add_argument("--check", action="store_true", help="boot self-check (GATE #1)")
    ap.add_argument("--chat", action="store_true", help="first real chat")
    ap.add_argument("--say", metavar="PROMPT",
                    help="one-shot chat: print only the reply (UI seam)")
    ap.add_argument("--task", metavar="GOAL",
                    help="first real task through the Task State Machine (GATE #5)")
    ap.add_argument("--task-dir", metavar="DIR", default=None,
                    help="task workspace root (default M:\\NEXUS-Test)")
    ap.add_argument("--ui-selftest", action="store_true",
                    help="first real chat window (GATE #6)")
    ap.add_argument("--tray-selftest", action="store_true",
                    help="real tray icon + menu (GATE #7)")
    ap.add_argument("--overlay-selftest", action="store_true",
                    help="real always-on-top overlay (GATE #8)")
    ap.add_argument("--tray", action="store_true",
                    help="PHASE 27: launch UI minimized to tray (production startup)")
    ap.add_argument("--ui", action="store_true",
                    help="PHASE 27: launch the desktop UI with the production tray")
    ap.add_argument("--phase27-selftest", action="store_true",
                    help="PHASE 27 production tray + startup selftest")
    ap.add_argument("--raise-existing", action="store_true",
                    help="PHASE 27: raise the running instance's window and exit")
    ap.add_argument("--remote", action="store_true",
                    help="PHASE 28: headless remote gateway node (phone -> core)")
    ap.add_argument("--phase28-selftest", action="store_true",
                    help="PHASE 28 remote gateway selftest (real HTTP loop)")
    ap.add_argument("--model-base", default="http://127.0.0.1:8080")
    ap.add_argument("--ollama-model", default="qwen3-mini",
                    help="model id for the Ollama MODE A2 adapter")
    args = ap.parse_args(argv)

    if args.phase28_selftest:
        try:
            import nexus_remote_gateway
            return nexus_remote_gateway.phase28_selftest(sys.modules[__name__])
        except BaseException as exc:  # noqa: BLE001 — honest crash, printed
            print(f"[x] selftest crashed (honest): {type(exc).__name__}: {exc}")
            traceback.print_exc()
            return 1
    if args.phase27_selftest:
        try:
            import nexus_ui
            return nexus_ui.phase27_selftest(sys.modules[__name__])
        except BaseException as exc:  # noqa: BLE001 — honest crash, printed
            print(f"[x] selftest crashed (honest): {type(exc).__name__}: {exc}")
            traceback.print_exc()
            return 1
    if args.raise_existing:
        try:
            import nexus_ui
            res = nexus_ui.p27_raise_existing()
            print("[i] raise-existing:", json.dumps(res, ensure_ascii=False))
            return 0 if res.get("ok") else 3
        except BaseException as exc:  # noqa: BLE001
            print(f"[x] raise-existing failed (honest): {type(exc).__name__}: {exc}")
            return 3
    if args.ui_selftest or args.tray_selftest or args.overlay_selftest:
        try:
            import nexus_ui
            if args.ui_selftest:
                return nexus_ui.ui_selftest(sys.modules[__name__])
            if args.tray_selftest:
                return nexus_ui.tray_selftest(sys.modules[__name__])
            return nexus_ui.overlay_selftest(sys.modules[__name__])
        except BaseException as exc:  # noqa: BLE001 — honest crash, printed
            print(f"[x] selftest crashed (honest): {type(exc).__name__}: {exc}")
            traceback.print_exc()
            return 1
    if args.task:
        return run_task(args.task, args.task_dir)
    if args.say:
        return say(args.say, args.model_base, args.ollama_model)
    if args.chat:
        return chat(args.model_base, args.ollama_model)

    if not acquire_lock():
        # PHASE 27 production behavior: raise the running window, exit honestly
        raised = False
        try:
            import nexus_ui
            res = nexus_ui.p27_raise_existing()
            raised = bool(res.get("ok"))
            print("[i] NEXUS already running — raise signal sent:",
                  json.dumps(res, ensure_ascii=False))
        except BaseException as exc:  # noqa: BLE001
            print(f"[x] another instance holds the lock; raise failed honestly: {exc}")
        return 0 if raised else 2
    banner()
    cert = boot_check()
    write_cert(cert)
    s = cert["core_summary"]
    print(f"core packages : {s['ok']} ok / {s['err']} err (of {len(CORE_MODULES)})")
    for mod, err in cert["core_probes"]["err"].items():
        print(f"  ERR {mod}: {err}")
    rt = cert["model_runtime"]
    print(f"model runtime : {'ONLINE' if rt.get('up') else 'offline'} at {rt.get('base')}")
    print(f"verdict       : {cert['verdict']}  ({cert['boot_seconds']}s)")
    print(f"certificate   : {CERT}")
    if args.check:
        release_lock()
        return 0 if cert["verdict"] == "PASS" else 1
    if args.remote:
        # PHASE 28 headless node: boot check already ran; serve the gateway
        try:
            import nexus_remote_gateway
            gw = nexus_remote_gateway.RemoteGateway(sys.modules[__name__])
            info = gw.start()
            print(f"[remote] gateway on 127.0.0.1:{info['port']} — token: "
                  f"{gw.token_path}")
            print("[remote] Ctrl+C to stop")
            while True:
                time.sleep(30)
                print(f"[remote] alive {time.strftime('%H:%M:%S')} · "
                      f"executed={gw.executed_count} · model={gw.model_status}")
        except KeyboardInterrupt:
            print("[remote] stopped by user")
        except BaseException as exc:  # noqa: BLE001 — honest crash
            print(f"[x] remote node crashed (honest): {type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            try:
                gw.stop()  # noqa: F821
            except BaseException:  # noqa: BLE001
                pass
            release_lock()
        return 0

    # PHASE 27 production launch: banner → boot check → REAL UI + production tray
    try:
        import tkinter as tk
        import nexus_ui
        root = tk.Tk()
        nexus_ui.NEXUS26App(root, sys.modules[__name__],
                            start_minimized=bool(args.tray))
        root.mainloop()
        release_lock()
        return 0
    except BaseException as exc:  # noqa: BLE001 — honest crash
        print(f"[x] UI crashed (honest): {type(exc).__name__}: {exc}")
        traceback.print_exc()
        release_lock()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())