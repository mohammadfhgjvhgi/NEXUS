# -*- coding: utf-8 -*-
"""Sample AGENT plugin — spec 36 manifest + spec 40 message transcript.

run(task, ctx) executes a REAL plan→act→verify loop:
  plan   : record the goal as an AgentMessage
  act    : write the file inside the jailed fs_root (permission: filesystem)
  verify : hash the file with the injected plugin_sha256 tool and compare
"""
import json
import os


def _msg(step, sender, receiver, status, data, evidence=None, confidence=1.0):
    return {"task_id": data.get("task_id"), "sender": sender,
            "receiver": receiver, "message_type": step, "status": status,
            "evidence": evidence or {}, "confidence": confidence,
            "data": {k: v for k, v in data.items() if k != "task_id"},
            "timestamp": os.environ.get("NEXUS_TS") or data.get("ts", "")}


def run(task, ctx):
    """task: {out_rel, content, task_id} · ctx: {tool_sha256, ts}"""
    fs_root = ctx["fs_root"]
    out = fs_root / str(task.get("out_rel") or "agent_out.txt")
    content = str(task.get("content") or "")
    transcript = []

    transcript.append(_msg("plan", "agent-file-writer", "master", "ok", {
        "task_id": task.get("task_id"), "ts": ctx.get("ts"),
        "goal": "write+verify file", "steps": 3, "content_bytes": len(content)}))

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    transcript.append(_msg("act", "agent-file-writer", "filesystem", "ok", {
        "task_id": task.get("task_id"), "ts": ctx.get("ts"),
        "path": str(out), "bytes": out.stat().st_size}))

    got = ctx["tool_sha256"]({"path": str(out)})["sha256"]
    want = ctx["tool_sha256"]({"text": content})["sha256"]
    ok = got == want
    transcript.append(_msg("verify", "agent-file-writer", "master",
                           "ok" if ok else "failed", {
        "task_id": task.get("task_id"), "ts": ctx.get("ts"),
        "sha256_file": got[:32], "sha256_expected": want[:32]}, None,
        1.0 if ok else 0.0))
    return {"completed": ok, "steps": len(transcript),
            "transcript": transcript, "path": str(out),
            "sha256": got}


def register(ctx):
    ctx.register_agent({
        "id": "file-writer-agent",
        "role": "Coder",
        "description": "Writes a jailed file and verifies it byte-exact",
        "model_policy": {"mode": "tool-only", "llm_required": False},
        "tools": ["plugin_sha256"],
        "skills": [],
        "permissions": ["filesystem"],
        "context_requirements": ["fs_root", "tool_sha256"],
        "input_schema": {"type": "object",
                         "properties": {"out_rel": {"type": "string"},
                                        "content": {"type": "string"}}},
        "output_schema": {"type": "object",
                          "properties": {"completed": {"type": "boolean"}}},
        "verification_rules": ["sha256_file == sha256(content)"],
        "run": run,
    })
