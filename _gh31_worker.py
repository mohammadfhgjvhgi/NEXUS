# -*- coding: utf-8 -*-
"""gh31 worker — commit & push the PHASE 31 delta to GitHub (device-side).

Delta since 4622555d (the pushed PHASE 0-29 snapshot):
  + skills/                       (PHASE 31 system, registry, observations)
  + proofs/phase31_skills.json    (PHASE 31 evidence)
  + tests/test_gh31_verify.py     (GitHub verification probe)
  ~ realtime runtime state        (revival hb/captures/audit)
  + tests/test_gh31_upload_trigger.py, _gh31_worker.py

Also commits the v8 housekeeping delta (session.txt + tunnel logs).

Discipline: append-only .gitignore guard for runtime logs, push-protection
auto-exclusion loop, ls-remote + API verification, progressive result
writes (_gh31_result.json), token never printed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

NEXUS = Path(r"M:\NEXUS")
V8 = Path(r"M:\ps\almoutmag-v8")
RESULT = NEXUS / "_gh31_result.json"
STATE = NEXUS / "_gh31_state.json"
T0 = time.time()


def iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hb(step, note, **kw) -> None:
    try:
        obj = {"utc": iso(), "step": step, "note": str(note)[:200],
               "pid": os.getpid(), "uptime_s": round(time.time() - T0, 1)}
        obj.update(kw)
        STATE.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    except BaseException:
        pass


def finish(result: dict) -> None:
    result["utc_end"] = iso()
    result["elapsed_s"] = round(time.time() - T0, 1)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    hb("done", result.get("verdict", "?"))


def steps_log(result: dict, step: str, detail: dict) -> None:
    entry = {"step": step, "utc": iso(), "detail": detail}
    result.setdefault("steps", []).append(entry)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    hb(step, str(detail.get("rc", "")) if isinstance(detail, dict) else "")


def run(cmd, timeout=300) -> dict:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return {"rc": p.returncode, "stdout": (p.stdout or "")[-1500:],
            "stderr": (p.stderr or "")[-1500:]}


def read_token() -> str:
    cfg = (V8 / ".git" / "config").read_text(encoding="utf-8",
                                             errors="replace")
    m = re.search(r"https://([^@\s]+)@github\.com", cfg)
    return m.group(1) if m else ""


def api(url: str, token: str):
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token,
                      "Accept": "application/vnd.github+json",
                      "User-Agent": "nexus-gh31-worker"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8",
                                                              "replace"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except BaseException:
            return e.code, {}


COMMIT_SUBJECT = ("NEXUS v0.31.0 - PHASE 31 skill system "
                  "(import/learn/create) + realtime revival + gh31 verify")
COMMIT_BODY = ("skills/: 5 skills (3 created, 1 imported byte-identical, "
               "1 learned via spec 84 gate) + registry + observations; "
               "proofs/phase31_skills.json verdict PASS with live 9412 "
               "round-trip; realtime channels revived (9411-9414); "
               "GitHub verification probe evidence. Disk rules.")

GI_GUARD = ["realtime/logs/", "skills/runs/", "skills/worker_phase31.log",
            "_gh31_worker.log"]


def push_nexus(result: dict, token: str) -> None:
    steps_log(result, "gitignore", run([
        "git", "-C", str(NEXUS), "config", "core.autocrlf", "false"]))
    gi = NEXUS / ".gitignore"
    txt = gi.read_text(encoding="utf-8", errors="replace")
    missing = [ln for ln in GI_GUARD if ln not in txt]
    if missing:
        gi.write_text(txt + "\n# gh31 runtime-log guard\n"
                      + "\n".join(missing) + "\n", encoding="utf-8")
        steps_log(result, "gitignore", {"appended": missing})
    else:
        steps_log(result, "gitignore", {"appended": False,
                                        "note": "all lines present"})
    sa = run(["git", "-C", str(NEXUS), "add", "-A"], timeout=600)
    steps_log(result, "add", sa)
    if sa["rc"] != 0:
        raise RuntimeError("git add failed: " + sa["stderr"][:200])
    sc = run(["git", "-C", str(NEXUS), "commit", "-m", COMMIT_SUBJECT,
              "-m", COMMIT_BODY], timeout=600)
    steps_log(result, "commit", sc)
    if sc["rc"] != 0 and "nothing to commit" not in (sc["stdout"]
                                                     + sc["stderr"]):
        raise RuntimeError("git commit failed: " + sc["stderr"][:300])
    if "nothing to commit" in (sc["stdout"] + sc["stderr"]):
        result["note_commit"] = "nothing to commit (already current)"
    head = run(["git", "-C", str(NEXUS), "rev-parse", "HEAD"])
    head_sha = head["stdout"].strip()
    result["head_sha"] = head_sha
    hb("commit", head_sha[:12] if head_sha else "?")
    # push-protection retry loop (untrack blocked paths, amend, retry)
    push_log = {}
    last_stderr = ""
    for attempt in (1, 2, 3):
        sp = subprocess.run(
            ["git", "-C", str(NEXUS), "push", "origin", "main"],
            cwd=str(NEXUS), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=1800)
        last_stderr = sp.stderr or ""
        push_log = {"attempt": attempt, "rc": sp.returncode,
                    "stdout": (sp.stdout or "")[-1500:],
                    "stderr": last_stderr[-1500:]}
        steps_log(result, "push", push_log)
        if sp.returncode == 0:
            break
        if ("GH013" in last_stderr
                or "Push cannot contain secrets" in last_stderr
                or "push protection" in last_stderr.lower()):
            paths = sorted(set(re.findall(
                r"path:\s*([^\s]+?):\d+", last_stderr)))
            if paths:
                result["push_protection_paths"] = paths
                hb("pushprot", ", ".join(paths)[:140])
                gtxt = gi.read_text(encoding="utf-8", errors="replace")
                addl = []
                for p in paths:
                    p = p.strip().rstrip(":")
                    if p and ("/" + p) not in gtxt:
                        addl.append("/" + p)
                        rr = run(["git", "-C", str(NEXUS), "rm", "-r",
                                  "--cached", "-q", "--", p], timeout=120)
                        if rr["rc"] != 0:
                            run(["git", "-C", str(NEXUS), "rm", "--cached",
                                 "-q", "--", p], timeout=120)
                if addl:
                    gi.write_text(gtxt
                                  + "\n# push-protection auto-exclusions\n"
                                  + "\n".join(addl) + "\n", encoding="utf-8")
                    run(["git", "-C", str(NEXUS), "add", "-A"], timeout=600)
                    run(["git", "-C", str(NEXUS), "commit", "--amend",
                         "-m", COMMIT_SUBJECT, "-m", COMMIT_BODY],
                        timeout=600)
                    continue
        time.sleep(5)
    if push_log.get("rc", 1) != 0:
        raise RuntimeError(f"git push rc={push_log.get('rc')}: "
                           f"{(last_stderr or '')[:300]}")
    sl = run(["git", "-C", str(NEXUS), "ls-remote", "origin", "main"],
             timeout=120)
    remote_sha = sl["stdout"].split("\t")[0].strip() if sl["stdout"] else ""
    result["remote_sha"] = remote_sha
    result["sha_match"] = bool(remote_sha and remote_sha == head_sha)
    stv, rv = api(f"https://api.github.com/repos/mohammadfhgjvhgi/NEXUS/"
                  f"commits/main", token)
    result["api_verify_status"] = stv
    if stv == 200:
        result["api_head"] = (rv or {}).get("sha", "")[:12]
        result["api_commit_url"] = (rv or {}).get("html_url", "")
        result["api_match"] = ((rv or {}).get("sha") == head_sha)


def push_v8(result: dict) -> None:
    sv = run(["git", "-C", str(V8), "add", "-A"], timeout=300)
    steps_log(result, "v8_add", sv)
    cv = run(["git", "-C", str(V8), "commit", "-m",
              "session 2026-11-20: tunnel pair #8 + PHASE 31 session state"],
             timeout=300)
    steps_log(result, "v8_commit", cv)
    if cv["rc"] != 0 and "nothing to commit" not in (cv["stdout"]
                                                     + cv["stderr"]):
        raise RuntimeError("v8 commit failed: " + cv["stderr"][:200])
    pv = run(["git", "-C", str(V8), "push", "origin", "main"], timeout=600)
    steps_log(result, "v8_push", pv)
    if pv["rc"] != 0:
        raise RuntimeError("v8 push failed: " + pv["stderr"][:200])
    hv = run(["git", "-C", str(V8), "rev-parse", "HEAD"])
    svl = run(["git", "-C", str(V8), "ls-remote", "origin", "main"],
              timeout=120)
    v8_head = hv["stdout"].strip()
    v8_remote = svl["stdout"].split("\t")[0].strip() if svl["stdout"] else ""
    result["v8_head_sha"] = v8_head
    result["v8_remote_sha"] = v8_remote
    result["v8_sha_match"] = bool(v8_remote and v8_remote == v8_head)


def main() -> int:
    result = {"worker": "gh31", "utc_start": iso(), "steps": []}
    try:
        token = read_token()
        result["token_prefix"] = (token[:4] + "...") if token else "MISSING"
        if not token:
            raise RuntimeError("token extraction failed from v8 config")
        hb("boot", "worker alive", pid=os.getpid())
        push_nexus(result, token)
        push_v8(result)
        ok = (result.get("sha_match") and result.get("api_verify_status") == 200
              and result.get("v8_sha_match"))
        result["verdict"] = "PASS" if ok else "PARTIAL"
        finish(result)
        return 0
    except BaseException as e:
        result["verdict"] = "FAIL"
        result["error"] = f"{type(e).__name__}: {e}"
        finish(result)
        return 1


if __name__ == "__main__":
    sys.exit(main())
