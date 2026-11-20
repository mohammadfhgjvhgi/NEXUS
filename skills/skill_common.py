# -*- coding: utf-8 -*-
"""NEXUS Skill System — PHASE 31 — contracts & context (stdlib only).

Spec alignment (NEXUS Master Technical Specification v1.0):
  §82  Skill System: a Skill is a reusable capability/workflow. Fields:
       Description, Inputs, Tools, Workflow, Verification, Version.
  §83  Skill Creation: Observe repeated workflow -> Extract candidate ->
       Create Skill -> Test -> Verify -> Register.
  §84  Skill Learning: a repeated task MAY become a skill only when it is
       (1) repeated (2) useful (3) verifiable (4) NOT tied to temporary
       information. All four gates are enforced here — named rejections.
  §240 Developer API surface lives in the manager (create/import/observe/
       promote/render/run); §241 spirit: run-jail + strict manifests.

Skill package layout on disk (M:\\NEXUS\\skills\\skills\\<name>\\):
  skill.json   manifest {name, version, description, inputs, tools,
               workflow, verification, source, executable}
  .meta.json   provenance {created_utc | imported_utc | learned_utc, actor,
               origin / origin_manifest_sha256 for imports}

Workflow steps (data-driven, no code in packages):
  {"op": "echo",           "text": "..."}    -> run: echo.json in run dir
  {"op": "write_note",     "name": "...", "text": "..."} -> file in run dir
  {"op": "append_journal", "text": "..."}    -> journal.jsonl in run dir
  {"op": "prompt",         "text": "..."}    -> render-only (no side effects)
Placeholders: {{input.<key>}} substituted from the inputs dict.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

PHASE = 31
VERSION = "0.31.0"

REQUIRED_FIELDS = ("name", "version", "description", "inputs", "tools",
                   "workflow", "verification")            # §82 fields
SOURCES = ("created", "imported", "learned")
OPS = ("echo", "write_note", "append_journal", "prompt")
EXEC_OPS = ("echo", "write_note", "append_journal")       # run-able (jailed)
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{2,47}$")
REPEAT_MIN = 3                                            # §84 gate (1)
PLACEHOLDER = re.compile(r"\{\{input\.([a-zA-Z0-9_]+)\}\}")


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append_jsonl(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: Path) -> list:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except BaseException:
                out.append({"_unparseable": line[:200]})
    return out


def validate_steps(workflow) -> list:
    """Validate a workflow list. Returns error list (empty = valid)."""
    errors = []
    if not isinstance(workflow, list) or not workflow:
        return ["workflow_empty_or_not_list"]
    for i, step in enumerate(workflow):
        if not isinstance(step, dict) or "op" not in step:
            errors.append(f"step_{i}_not_dict_or_missing_op")
            continue
        op = step.get("op")
        if op not in OPS:
            errors.append(f"step_{i}_bad_op:{op}")
            continue
        if op in ("echo", "write_note", "append_journal", "prompt") \
                and not str(step.get("text") or "").strip():
            errors.append(f"step_{i}_missing_text")
        if op == "write_note" and not str(step.get("name") or "").strip():
            errors.append(f"step_{i}_missing_name")
    return errors


def validate_manifest(m, expect_source=True) -> tuple:
    """§82-shaped manifest validation. Returns (ok, errors[], sha256)."""
    errors = []
    if not isinstance(m, dict):
        return False, ["manifest_not_object"], ""
    for k in REQUIRED_FIELDS:
        if k not in m or (isinstance(m[k], str) and not m[k].strip()):
            errors.append(f"missing_{k}")
    if errors:
        return False, errors, ""
    if not SLUG.match(str(m["name"])):
        errors.append("bad_name_slug")
    if not isinstance(m["version"], str) or not m["version"].strip():
        errors.append("bad_version")
    if not isinstance(m["inputs"], dict):
        errors.append("inputs_not_dict")
    if not isinstance(m["tools"], list):
        errors.append("tools_not_list")
    errors.extend(validate_steps(m["workflow"]))
    if not isinstance(m["verification"], str) or not m["verification"].strip():
        errors.append("bad_verification")
    src = m.get("source")
    if expect_source and src not in SOURCES:
        errors.append("bad_source:" + str(src))
    if "executable" in m and not isinstance(m["executable"], bool):
        errors.append("executable_not_bool")
    raw = json.dumps(m, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return (not errors), errors, sha256_bytes(raw)


def render_text(template: str, inputs: dict) -> str:
    """Substitute {{input.key}}; undefined placeholder -> named error."""
    def sub(match):
        key = match.group(1)
        if key not in inputs:
            raise KeyError(f"undefined_input:{key}")
        return str(inputs[key])
    return PLACEHOLDER.sub(sub, template)


def render_workflow(workflow, inputs: dict) -> tuple:
    """Render all steps. Returns (rendered_steps, errors[])."""
    out, errors = [], []
    for i, step in enumerate(workflow):
        try:
            s = dict(step)
            if "text" in s:
                s["text"] = render_text(str(s["text"]), inputs)
            if s.get("op") == "write_note" and "name" in s:
                s["name"] = render_text(str(s["name"]), inputs)
            out.append(s)
        except KeyError as exc:
            errors.append(f"step_{i}_{exc.args[0]}")
    return out, errors


def safe_name(name: str) -> str:
    """Sanitize a rendered file name for the run jail."""
    keep = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("._")
    return keep[:80] or "note.txt"
