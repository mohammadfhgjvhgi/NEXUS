# -*- coding: utf-8 -*-
"""NEXUS Skill System — PHASE 31 — store & lifecycle engine (stdlib only).

SkillStore paths (home = M:\\NEXUS\\skills on the device):
  home\\skills\\<name>\\skill.json   — skill packages (§82 manifests)
  home\\skills\\<name>\\.meta.json   — provenance
  home\\staging\\...                 — landing zone for foreign packages
  home\\runs\\<skill>\\<stamp>\\     — run jail (§241 spirit)
  home\\registry.json               — discovered registry + evidence
  home\\observations.jsonl          — append-only learning journal (§83/§84)

Lifecycle operations (all evidenced, all named on rejection):
  discover()            scan packages, validate manifests, hash files
  create_skill()        §83 direct creation path
  import_skill()        import a foreign package (byte-identity + provenance)
  record_observation()  append a learning observation
  promote_observation() §84 gate -> candidate -> test -> verify -> register
  render_skill()        §82 render (dry — no side effects)
  run_skill()           jailed execution of an executable skill
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from skill_common import (EXEC_OPS, PHASE, REPEAT_MIN, SLUG, SOURCES,   # noqa: E402
                          VERSION, append_jsonl, atomic_json, read_json,
                          read_jsonl, render_workflow, safe_name,
                          sha256_bytes, sha256_file, utcnow,
                          validate_manifest)


class SkillError(Exception):
    """Named lifecycle rejection — never silent."""


class SkillStore:
    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.store = self.home / "skills"
        self.staging = self.home / "staging"
        self.runs = self.home / "runs"
        self.registry_path = self.home / "registry.json"
        self.observations_path = self.home / "observations.jsonl"

    # ------------------------------------------------------------- paths
    def skill_dir(self, name: str) -> Path:
        # SLUG forbids separators/dots -> path escape impossible after this
        if not SLUG.match(str(name)):
            raise SkillError(f"bad_name_slug:{name}")
        return self.store / name

    def _check_name_free(self, name: str) -> None:
        if (self.store / name).exists():
            raise SkillError(f"name_exists:{name}")

    # ---------------------------------------------------------- discover
    def discover(self) -> list:
        entries = []
        if not self.store.is_dir():
            return entries
        for d in sorted(self.store.iterdir()):
            if not d.is_dir() or d.name.startswith(("_", ".")):
                continue
            mpath = d / "skill.json"
            if not mpath.is_file():
                entries.append({"name": d.name, "status": "invalid",
                                "errors": ["manifest_missing"]})
                continue
            try:
                m = read_json(mpath)
            except BaseException as exc:
                entries.append({"name": d.name, "status": "invalid",
                                "errors": [f"manifest_unreadable:"
                                           f"{type(exc).__name__}"]})
                continue
            ok, errors, msha = validate_manifest(m)
            files = {}
            for f in sorted(d.iterdir()):
                if f.is_file():
                    files[f.name] = {"size": f.stat().st_size,
                                     "sha256": sha256_file(f)}
            meta = {}
            try:
                meta = read_json(d / ".meta.json")
            except BaseException:
                meta = {}
            entries.append({
                "name": d.name, "status": "valid" if ok else "invalid",
                "errors": errors, "manifest": m, "manifest_sha256": msha,
                "files": files, "meta": meta,
                "version": str(m.get("version")),
                "source": m.get("source"),
                "executable": bool(m.get("executable")),
            })
        return entries

    # ------------------------------------------------------------ create
    def create_skill(self, spec: dict, actor: str = "phase31",
                     source: str = "created") -> dict:
        """§83 Create -> Test -> Verify -> Register (creation path)."""
        m = dict(spec)
        m["source"] = source if source in SOURCES else "created"
        if "executable" not in m:
            m["executable"] = all(
                s.get("op") in EXEC_OPS for s in m.get("workflow", []))
        ok, errors, msha = validate_manifest(m)
        if not ok:
            raise SkillError("manifest_invalid:" + ";".join(errors))
        self._check_name_free(m["name"])
        d = self.skill_dir(m["name"])
        d.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(m, ensure_ascii=False, indent=1) + "\n"
        (d / "skill.json").write_text(raw, encoding="utf-8")
        meta = {"created_utc": utcnow(), "actor": actor,
                "manifest_sha256": msha}
        atomic_json(d / ".meta.json", meta)
        # verify what landed on disk
        ok2, errors2, msha2 = validate_manifest(read_json(d / "skill.json"))
        if not ok2 or msha2 != msha:
            raise SkillError("post_write_mismatch")
        return {"name": m["name"], "dir": str(d), "manifest_sha256": msha,
                "source": m["source"], "executable": m["executable"]}

    # ------------------------------------------------------------ import
    def import_skill(self, src: Path, actor: str = "phase31") -> dict:
        """Import a foreign package: byte-identity + full provenance."""
        src = Path(src)
        if src.is_dir():
            mpath = src / "skill.json"
        else:
            mpath = src
        if not mpath.is_file():
            raise SkillError(f"source_manifest_missing:{str(src)}")
        origin_bytes = mpath.read_bytes()
        origin_sha = sha256_bytes(origin_bytes)
        try:
            m = json.loads(origin_bytes.decode("utf-8"))
        except BaseException as exc:
            raise SkillError(f"source_unreadable:{type(exc).__name__}")
        ok, errors, _ = validate_manifest(m)
        if not ok:
            raise SkillError("source_manifest_invalid:" + ";".join(errors))
        self._check_name_free(m["name"])
        d = self.skill_dir(m["name"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "skill.json").write_bytes(origin_bytes)   # byte-identical copy
        if src.is_dir():
            for f in sorted(src.iterdir()):
                if f.is_file() and f.name not in ("skill.json", ".meta.json"):
                    (d / f.name).write_bytes(f.read_bytes())
        atomic_json(d / ".meta.json", {
            "imported_utc": utcnow(), "actor": actor,
            "origin": str(src), "origin_manifest_sha256": origin_sha})
        stored = (d / "skill.json").read_bytes()
        if sha256_bytes(stored) != origin_sha:
            raise SkillError("byte_identity_failed")
        return {"name": m["name"], "dir": str(d),
                "origin": str(src), "origin_manifest_sha256": origin_sha,
                "byte_identity": True, "version": str(m.get("version"))}

    # -------------------------------------------------------------- learn
    def record_observation(self, obs: dict) -> dict:
        req = ("repeat_key", "summary", "steps", "useful", "verifiable",
               "temporary_info")
        missing = [k for k in req if k not in obs]
        if missing:
            raise SkillError("observation_missing:" + ";".join(missing))
        if not SLUG.match(str(obs["repeat_key"])):
            raise SkillError(f"bad_repeat_key:{obs['repeat_key']}")
        if not isinstance(obs["steps"], list) or not obs["steps"]:
            raise SkillError("observation_steps_empty")
        entry = dict(obs)
        entry["utc"] = obs.get("utc") or utcnow()
        entry["actor"] = obs.get("actor") or "phase31"
        append_jsonl(self.observations_path, entry)
        return {"repeat_key": obs["repeat_key"], "utc": entry["utc"]}

    def observations_for(self, repeat_key: str) -> list:
        return [o for o in read_jsonl(self.observations_path)
                if o.get("repeat_key") == repeat_key]

    def _gate(self, obs: list) -> list:
        """§84 gate — named reasons for every rejection."""
        reasons = []
        if len(obs) < REPEAT_MIN:
            reasons.append(f"not_repeated:{len(obs)}<{REPEAT_MIN}")
        if any(not o.get("useful") for o in obs):
            reasons.append("not_useful")
        if any(not o.get("verifiable") for o in obs):
            reasons.append("not_verifiable")
        if any(o.get("temporary_info") for o in obs):
            reasons.append("temporary_info")
        return reasons

    def promote_observation(self, repeat_key: str,
                            actor: str = "phase31") -> dict:
        """§83/§84: Observe -> Extract candidate -> Test -> Verify ->
        Register. Honest REJECTED result with named reasons."""
        obs = self.observations_for(repeat_key)
        reasons = self._gate(obs)
        if reasons:
            return {"repeat_key": repeat_key, "status": "REJECTED",
                    "reasons": reasons, "observations": len(obs)}
        steps = []
        seen = set()
        for o in obs:
            for s in o.get("steps", []):
                key = json.dumps(s, ensure_ascii=False, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    steps.append(s)
        manifest = {
            "name": repeat_key,
            "version": "1.0.0",
            "description": str(obs[0].get("summary"))[:300],
            "inputs": {},
            "tools": sorted({s.get("op") for s in steps if s.get("op")}),
            "workflow": steps,
            "verification": (f"replay_observations_and_hash_outputs;"
                             f"observations={len(obs)}"),
            "source": "learned",
            "executable": all(s.get("op") in EXEC_OPS for s in steps),
        }
        ok, errors, msha = validate_manifest(manifest)   # TEST
        if not ok:
            return {"repeat_key": repeat_key, "status": "REJECTED",
                    "reasons": [f"candidate_invalid:{e}" for e in errors],
                    "observations": len(obs)}
        reasons2 = self._gate(self.observations_for(repeat_key))  # VERIFY
        if reasons2:
            return {"repeat_key": repeat_key, "status": "REJECTED",
                    "reasons": ["gate_changed:" + ";".join(reasons2)],
                    "observations": len(obs)}
        try:
            reg = self.create_skill(manifest, actor=actor, source="learned")
        except SkillError as exc:
            return {"repeat_key": repeat_key, "status": "REJECTED",
                    "reasons": [f"register:{exc}"], "observations": len(obs)}
        reg["evidence"] = {"observations": len(obs),
                           "first_utc": obs[0].get("utc"),
                           "last_utc": obs[-1].get("utc"),
                           "manifest_sha256": msha}
        reg["status"] = "REGISTERED"
        return reg

    # ------------------------------------------------------------- render
    def render_skill(self, entry: dict, inputs: dict) -> dict:
        m = entry.get("manifest") or {}
        rendered, errors = render_workflow(m.get("workflow", []), inputs)
        return {"name": entry.get("name"), "rendered": rendered,
                "errors": errors, "ok": not errors}

    # ---------------------------------------------------------------- run
    def run_skill(self, entry: dict, inputs: dict,
                  actor: str = "phase31") -> dict:
        """Jailed execution (§241 spirit). Only executable skills run."""
        m = entry.get("manifest") or {}
        if not m.get("executable"):
            raise SkillError(f"not_executable:{entry.get('name')}")
        rendered, errors = render_workflow(m.get("workflow", []), inputs)
        if errors:
            raise SkillError("render_errors:" + ";".join(errors))
        stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        run_dir = self.runs / str(entry.get("name")) / stamp
        run_dir.mkdir(parents=True, exist_ok=True)
        jail = str(run_dir)
        outputs = []
        for i, step in enumerate(rendered):
            op = step.get("op")
            if op == "echo":
                p = run_dir / f"echo_{i}.json"
                atomic_json(p, {"text": step.get("text", ""),
                                "op": "echo", "utc": utcnow()})
            elif op == "write_note":
                p = run_dir / safe_name(step.get("name", "note.txt"))
                p.write_text(str(step.get("text", "")), encoding="utf-8")
            elif op == "append_journal":
                p = run_dir / "journal.jsonl"
                append_jsonl(p, {"text": step.get("text", ""),
                                 "utc": utcnow()})
            else:
                raise SkillError(f"run_step_not_executable:{op}")
            outputs.append({"step": i, "op": op, "path": str(p),
                            "sha256": sha256_file(p),
                            "jailed": str(p).startswith(jail)})
        return {"name": entry.get("name"), "run_dir": str(run_dir),
                "outputs": outputs, "utc": utcnow(), "actor": actor}

    # ----------------------------------------------------------- registry
    def write_registry(self, entries: list, extra: dict) -> dict:
        valid = [e for e in entries if e.get("status") == "valid"]
        by_source = {}
        for e in valid:
            by_source[e.get("source") or "?"] = \
                by_source.get(e.get("source") or "?", 0) + 1
        obj = {
            "generated_utc": utcnow(), "phase": PHASE, "version": VERSION,
            "store_root": str(self.store),
            "counts": {"total": len(valid),
                       "invalid": len(entries) - len(valid),
                       "executable": sum(1 for e in valid
                                         if e.get("executable")),
                       "render_only": sum(1 for e in valid
                                          if not e.get("executable")),
                       "by_source": by_source},
            "skills": [{
                "name": e["name"], "version": e.get("version"),
                "source": e.get("source"),
                "executable": e.get("executable"),
                "manifest_sha256": e.get("manifest_sha256"),
                "files": sorted((e.get("files") or {}).keys()),
                "meta": e.get("meta"),
            } for e in valid],
            "observations_total": len(read_jsonl(self.observations_path)),
            **(extra or {}),
        }
        atomic_json(self.registry_path, obj)
        return obj


# ------------------------------------------------------------ integration
def events_token(home: Path) -> str:
    tok = Path(home).parent / "realtime" / "token.txt"   # M:\NEXUS\realtime
    try:
        return tok.read_text(encoding="utf-8").strip()
    except BaseException:
        return "ps1-stable-token-2026"


def events_pub(home: Path, event: dict, timeout=10) -> dict:
    url = "http://127.0.0.1:9412/events/pub"
    req = urllib.request.Request(
        url, data=json.dumps(event).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + events_token(home)},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def events_verify(home: Path, event_id: int, etype: str,
                  timeout=10) -> dict:
    url = (f"http://127.0.0.1:9412/events/stream"
           f"?cursor={max(0, event_id - 1)}&wait_s=3")
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + events_token(home)})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    hit = any(e.get("id") == event_id and e.get("type") == etype
              for e in data.get("events", []))
    return {"ok": hit, "count": len(data.get("events", [])),
            "cursor": data.get("cursor")}
