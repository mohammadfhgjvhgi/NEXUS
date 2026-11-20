"""C-RELIEF detached worker — survives MCP service restarts.

Spawned detached by test_c_spawn.py. Never talks to the network.
    python worker.py <phase> <name> <src> <dst>
    python worker.py recon

Phases: copy | verify | sha | purge | finalize  (same contracts as v6)
Recon:  full device audit -> M:\\NEXUS\\proofs\\device_audit.json
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import traceback
from pathlib import Path

BASE = Path(r"M:\NEXUS\tools\c_relief")
RESULTS = BASE / "results"
MANIFEST = Path(r"M:\C-RELIEF\MANIFEST.jsonl")
AUDIT = Path(r"M:\NEXUS\proofs\device_audit.json")


def hb(name: str, phase: str, detail: str = "") -> None:
    try:
        with open(RESULTS / (name + ".phases.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "phase": f"detached:{phase}", "detail": detail[:300]},
                                ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def finish(name: str, phase: str, result: dict, t0: float) -> None:
    result["phase"] = phase
    result["seconds"] = round(time.time() - t0, 1)
    (RESULTS / f"{name}__{phase}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    hb(name, f"{phase}_result", f"status={result.get('status')}")


def walk(root: str) -> tuple[int, int, dict]:
    count, total = 0, 0
    files: dict = {}
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            sz = entry.stat(follow_symlinks=False).st_size
                            count += 1
                            total += sz
                            files[os.path.relpath(entry.path, root).lower()] = sz
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return count, total, files


def superset(src: str, dst: str) -> tuple[dict, list]:
    sc, sb, sf = walk(src)
    dc, db, df = walk(dst)
    missing = [k for k, v in sf.items() if df.get(k) != v]
    return ({"src_files": sc, "src_bytes": sb, "dst_files": dc, "dst_bytes": db,
             "src_missing_in_dst": len(missing)}, missing)


def rm_ro(func, path, _exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def sha_file(p: str, deadline: float) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
            if time.time() > deadline:
                raise TimeoutError
    return h.hexdigest()


def robocopy(args: list[str], timeout: int = 6000) -> subprocess.CompletedProcess:
    return subprocess.run(["robocopy"] + args, capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ phases

def ph_copy(name, src, dst, t0):
    result = {"name": name, "status": "unknown"}
    if not os.path.isdir(src) or os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_done_or_missing"
        return result
    hb(name, "copy_begin")
    proc = robocopy([src, dst, "/E", "/COPY:DAT", "/DCOPY:DAT",
                     "/R:0", "/W:0", "/XJ", "/NFL", "/NDL", "/NP", "/MT:8"])
    result["robocopy_exit"] = proc.returncode
    hb(name, "copy_done", f"exit={proc.returncode}")
    result["status"] = "copied" if proc.returncode < 8 else "copy_failed"
    if proc.returncode >= 8:
        result["robocopy_tail"] = (proc.stdout or "")[-600:]
    return result


def ph_verify(name, src, dst, t0):
    result = {"name": name, "status": "unknown"}
    if not os.path.isdir(src) or os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_done_or_missing"
        return result
    hb(name, "verify_begin")
    summary, missing = superset(src, dst)
    result.update(summary)
    hb(name, "verify_walk_done", f"src={summary['src_files']}f/{summary['src_bytes']}B "
                                 f"dst={summary['dst_files']}f/{summary['dst_bytes']}B")
    result["status"] = "verified" if not missing else "copy_incomplete"
    if missing:
        result["missing_sample"] = missing[:10]
    return result


def ph_sha(name, src, dst, t0):
    result = {"name": name, "status": "unknown"}
    if not os.path.isdir(src) or os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_done_or_missing"
        return result
    checked, bad, aborted = 0, [], 0
    stack = [src]
    phase_deadline = time.time() + 1500  # detached: generous budget, still bounded
    while stack and checked < 12 and time.time() < phase_deadline:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    if checked >= 12 or time.time() >= phase_deadline:
                        break
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            if entry.stat(follow_symlinks=False).st_size >= 100 * 1024 * 1024:
                                rel = os.path.relpath(entry.path, src)
                                try:
                                    a = sha_file(entry.path, time.time() + 240)
                                    b = sha_file(os.path.join(dst, rel), time.time() + 240)
                                    checked += 1
                                    hb(name, "sha_file", f"{checked} {rel[:80]}")
                                    if a != b:
                                        bad.append(rel)
                                except TimeoutError:
                                    aborted += 1
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    result["sha_checked"] = checked
    result["sha_bad"] = bad
    result["sha_aborted_by_deadline"] = aborted
    result["status"] = "sha_ok" if not bad else "verify_failed"
    hb(name, "sha_done", f"checked={checked} bad={len(bad)} aborted={aborted}")
    return result


def ph_purge(name, src, dst, t0):
    result = {"name": name, "status": "unknown"}
    if not os.path.exists(src):
        result["status"] = "already_done_or_missing"
        return result
    if os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_junction"
        return result
    hb(name, "purge_selfverify_begin")
    summary, missing = superset(src, dst)
    result.update(summary)
    if missing:
        result["status"] = "purge_aborted_not_verified"
        result["missing_sample"] = missing[:10]
        hb(name, "purge_aborted", f"missing={len(missing)}")
        return result
    hb(name, "purge_begin", f"files_to_delete={summary['src_files']}")
    empty = BASE / "_empty"
    empty.mkdir(parents=True, exist_ok=True)
    try:
        proc2 = robocopy([str(empty), src, "/MIR", "/R:0", "/W:0",
                          "/XJ", "/NFL", "/NDL", "/NP", "/MT:8"])
        result["purge_exit"] = proc2.returncode
    except Exception as exc:  # noqa: BLE001
        result["purge_exit"] = f"exc:{exc}"[:120]
    hb(name, "purge_done", f"exit={result.get('purge_exit')}")
    removed = False
    for attempt in range(5):
        try:
            shutil.rmtree(src, onerror=rm_ro)
            removed = True
            break
        except OSError as exc:
            result["remove_error"] = str(exc)[:200]
            time.sleep(3)
    result["husk_removed"] = removed
    result["status"] = "purged" if removed else "remove_partial_locked"
    return result


def ph_finalize(name, src, dst, t0):
    result = {"name": name, "status": "unknown"}
    if os.path.exists(src) and os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_junction"
        result["junction_ok"] = True
        return result
    if os.path.exists(src):
        try:
            leftovers = os.listdir(src)
        except OSError as exc:
            result["status"] = "finalize_aborted_listdir"
            result["listdir_err"] = str(exc)[:120]
            return result
        if leftovers:
            result["status"] = "finalize_aborted_not_empty"
            result["leftover_sample"] = leftovers[:10]
            return result
        try:
            os.rmdir(src)
        except OSError as exc:
            result["status"] = "rmdir_failed"
            result["rmdir_err"] = str(exc)[:150]
            return result
    mk = subprocess.run(["cmd", "/c", "mklink", "/J", src, dst],
                        capture_output=True, text=True, timeout=30)
    result["mklink_rc"] = mk.returncode
    result["mklink_out"] = ((mk.stdout or "") + (mk.stderr or ""))[:200]
    ok = mk.returncode == 0 and os.path.realpath(src).lower() == dst.lower()
    result["junction_ok"] = ok
    result["status"] = "moved" if ok else "junction_failed"
    if ok:
        merged: dict = {"name": name, "src": src, "dst": dst}
        for ph in ("copy", "verify", "sha", "purge"):
            pf = RESULTS / f"{name}__{ph}.json"
            try:
                if pf.exists():
                    merged.update(json.loads(pf.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                pass
        with open(MANIFEST, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**merged,
                                 "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                ensure_ascii=False) + "\n")
    return result


PHASES = {"copy": ph_copy, "verify": ph_verify, "sha": ph_sha,
          "purge": ph_purge, "finalize": ph_finalize}


def run_phase(phase: str, name: str, src: str, dst: str) -> None:
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    hb(name, f"detached_{phase}_start", f"pid={os.getpid()}")
    try:
        result = PHASES[phase](name, src, dst, t0)
        finish(name, phase, result, t0)
    except BaseException as exc:  # noqa: BLE001
        hb(name, f"detached_{phase}_exception",
           f"{type(exc).__name__}: {exc} | {traceback.format_exc()[-350:]}")
        finish(name, phase, {"name": name, "status": "exception",
                             "error": f"{type(exc).__name__}: {exc}"[:300]}, t0)


# ------------------------------------------------------------------ recon

def dir_size(path: str, big_files: list | None = None, min_big: int = 300 * 1024 * 1024) -> int:
    total = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            sz = entry.stat(follow_symlinks=False).st_size
                            total += sz
                            if big_files is not None and sz >= min_big:
                                big_files.append({"path": entry.path, "gb": round(sz / 1024**3, 3)})
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def safe_children_gb(root: str, floor_gb: float, big: list | None = None) -> dict:
    out = {}
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        p = os.path.join(root, name)
        try:
            if os.path.islink(p) or not os.path.isdir(p):
                continue
            sz = dir_size(p, big)
            if sz / 1024**3 >= floor_gb:
                out[p] = round(sz / 1024**3, 2)
        except OSError:
            continue
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def run_recon() -> None:
    t0 = time.time()
    result: dict = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    big: list = []
    try:
        import shutil as sh
        result["drives"] = {}
        for letter in ("C:", "M:"):
            u, _t, f = sh.disk_usage(letter + "\\")
            result["drives"][letter] = {"used_gb": round(u / 1024**3, 1),
                                        "free_gb": round(f / 1024**3, 2)}
    except Exception as exc:  # noqa: BLE001
        result["drives"] = {"error": str(exc)}

    # system-level space hogs
    for label, p in (("pagefile", r"C:\pagefile.sys"), ("hiberfil", r"C:\hiberfil.sys"),
                     ("swapfile", r"C:\swapfile.sys")):
        try:
            result[label + "_gb"] = round(os.stat(p).st_size / 1024**3, 2)
        except OSError:
            result[label + "_gb"] = None

    profiles: dict = {}
    try:
        for name in os.listdir("C:\\Users"):
            p = os.path.join("C:\\Users", name)
            try:
                if os.path.islink(p) or not os.path.isdir(p):
                    continue
                profiles[p] = round(dir_size(p, big) / 1024**3, 2)
            except OSError:
                continue
    except OSError:
        pass
    result["profiles_gb"] = dict(sorted(profiles.items(), key=lambda kv: -kv[1]))

    real = {k: v for k, v in profiles.items()
            if "All Users" not in k and "Default" not in k and v > 1}
    top = max(real, key=real.get) if real else None
    if top:
        result["profile"] = top
        result["profile_level1_gb"] = safe_children_gb(top, 0.2, big)
        result["appdata_local_gb"] = safe_children_gb(os.path.join(top, "AppData", "Local"), 0.3, big)
        result["appdata_roaming_gb"] = safe_children_gb(os.path.join(top, "AppData", "Roaming"), 0.3, big)
        # junction-aware re-check of known moved paths
        moved = {}
        for label, rel in ((".cache", ".cache"), (".gradle", ".gradle"), (".codeium", ".codeium"),
                           (".pm2", ".pm2"), (".lmstudio", ".lmstudio"),
                           ("Arduino15", r"AppData\Local\Arduino15"),
                           (".mimo_storage", ".mimo_storage")):
            p = os.path.join(top, rel)
            if os.path.exists(p):
                moved[label] = {"junction": os.path.realpath(p).lower() != p.lower()}
        result["moved_paths_status"] = moved

    for label, p in (("ProgramData", r"C:\ProgramData"),
                     ("Windows", r"C:\Windows"), ("ProgramFiles", r"C:\Program Files"),
                     ("ProgramFiles86", r"C:\Program Files (x86)")):
        try:
            if os.path.isdir(p):
                result[label + "_gb"] = round(dir_size(p, big) / 1024**3, 2)
        except OSError:
            result[label + "_gb"] = None

    big.sort(key=lambda x: -x["gb"])
    seen: set = set()
    uniq = []
    for b in big:
        if b["path"] not in seen:
            seen.add(b["path"])
            uniq.append(b)
    result["big_files_over_300mb"] = uniq[:80]
    result["recon_seconds"] = round(time.time() - t0, 1)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) >= 2 and sys.argv[1] == "recon":
        try:
            run_recon()
        except BaseException as exc:  # noqa: BLE001
            AUDIT.write_text(json.dumps({"status": "exception",
                                         "error": f"{type(exc).__name__}: {exc}"[:300]},
                                        ensure_ascii=False), encoding="utf-8")
        return 0
    if len(sys.argv) >= 5:
        phase, name, src, dst = sys.argv[1:5]
        run_phase(phase, name, src, dst)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
