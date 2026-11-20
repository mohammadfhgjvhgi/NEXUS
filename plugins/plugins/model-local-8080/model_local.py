# -*- coding: utf-8 -*-
"""Sample MODEL plugin — local OpenAI-compatible provider (spec §33 area).

health() probes /v1/models · complete() runs a tiny chat completion.
Honest either way — an offline backend is a DEGRADED verdict, not a lie.
"""
import json
import urllib.request
from pathlib import Path

# model ladder discovery: ui_settings port first, then common local ports
BASES = ["http://127.0.0.1:8080/v1", "http://127.0.0.1:1234/v1",
         "http://127.0.0.1:11434/v1"]
TIMEOUT = 8
ACTIVE = {"base": None}


def health():
    last = None
    for base in BASES:
        try:
            req = urllib.request.Request(base + "/models")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
            ACTIVE["base"] = base
            return {"ok": True, "models": ids[:10], "http": resp.status,
                    "endpoint": base}
        except BaseException as exc:  # noqa: BLE001
            last = f"{base}: {type(exc).__name__}"[:160]
    return {"ok": False, "reason": last or "no_backend"}


def complete(model, prompt, max_tokens=16, timeout=40):
    base = ACTIVE.get("base") or BASES[0]
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0}).encode()
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        txt = (((data.get("choices") or [{}])[0].get("message") or {})
               .get("content") or "")
        return {"ok": True, "text": txt[:200], "model": data.get("model")}
    except BaseException as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}


def register(ctx):
    ctx.register_model({
        "id": "local-openai-ladder", "kind": "openai-compatible",
        "endpoint": BASES[0], "discovery": BASES,
        "health": health, "complete": complete,
    })
