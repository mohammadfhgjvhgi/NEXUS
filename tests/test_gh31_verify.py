# -*- coding: utf-8 -*-
"""PHASE 31 GitHub verification probe (read-only).

For each repo (M:\\NEXUS and M:\\ps\\almoutmag-v8):
  - local HEAD (hash + subject)
  - remote origin URL (credential-free)
  - ahead/behind vs origin/main (as of last fetch)
  - GitHub API remote HEAD (authoritative, via device token)
  - working-tree status count + top changed paths
Writes M:\\NEXUS\\proofs\\gh31_verify.json — evidence, no assertions on
match (the probe reports the truth; the push decision is separate).
"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

GIT = r"C:\Program Files\Git\cmd\git.EXE"
ROOT = Path(r"M:\NEXUS")
V8 = Path(r"M:\ps\almoutmag-v8")
OUT = ROOT / "proofs" / "gh31_verify.json"


def git(repo: Path, *args) -> dict:
    p = subprocess.run([GIT, "-C", str(repo), *args],
                       capture_output=True, text=True, timeout=90)
    return {"rc": p.returncode, "out": p.stdout.strip(),
            "err": p.stderr.strip()[:300]}


def api_json(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token,
                      "User-Agent": "nexus31-gh-probe",
                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def clean_remote(url: str) -> str:
    u = urllib.parse.urlparse(url)
    return f"https://{u.hostname}/{u.path.strip('/')}"


def read_token() -> str:
    """Token embedded in the v8 git remote URL (device-side only, never
    printed — mirrors _gh30_worker.py's extraction)."""
    cfg = (V8 / ".git" / "config").read_text(encoding="utf-8",
                                              errors="replace")
    m = re.search(r"https://([^@\s]+)@github\.com", cfg)
    return m.group(1) if m else ""


def probe(repo: Path, token: str, branch: str = "main") -> dict:
    out: dict = {"repo": str(repo)}
    out["exists"] = (repo / ".git").exists()
    if not out["exists"]:
        return out
    out["local_head"] = git(repo, "log", "-1", "--format=%H")
    out["local_subject"] = git(repo, "log", "-1", "--format=%s")["out"][:120]
    out["branch"] = git(repo, "rev-parse", "--abbrev-ref", "HEAD")["out"]
    rem = git(repo, "config", "--get", "remote.origin.url")
    out["origin_url"] = clean_remote(rem["out"]) if rem["out"] else None
    ab = git(repo, "rev-list", "--left-right", "--count",
             f"{branch}...origin/{branch}")
    if ab["rc"] == 0:
        parts = ab["out"].split()
        out["ahead_of_last_fetch"] = int(parts[0]) if parts else None
        out["behind_last_fetch"] = int(parts[1]) if len(parts) > 1 else None
    st = git(repo, "status", "--porcelain")
    lines = [l for l in st["out"].splitlines() if l.strip()]
    out["status_count"] = len(lines)
    out["status_top15"] = lines[:15]
    if out["origin_url"] and "github.com/" in out["origin_url"]:
        slug = out["origin_url"].split("github.com/", 1)[1].strip("/")
        if slug.endswith(".git"):
            slug = slug[:-4]                      # API path has no .git
        out["owner_repo"] = slug
        try:
            data = api_json(
                f"https://api.github.com/repos/{slug}/commits/{branch}",
                token)
            out["remote_head_sha"] = data.get("sha")
            out["remote_head_msg"] = ((data.get("commit") or {}).get(
                "message") or "")[:120]
            out["head_match"] = (out["local_head"].get("out") or
                                 "") == data.get("sha")
        except BaseException as exc:  # noqa: BLE001
            out["remote_head_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out


def test_gh31_verify() -> None:
    token = read_token()
    import time as _t
    report = {
        "probe": "gh31_verify",
        "utc": _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()),
        "token_present": bool(token),
        "nexus": probe(ROOT, token),
        "almoutmag_v8": probe(V8, token),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    assert OUT.is_file()
