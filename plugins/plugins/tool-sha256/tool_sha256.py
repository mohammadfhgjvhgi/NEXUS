# -*- coding: utf-8 -*-
"""Sample TOOL plugin — registers plugin_sha256 (spec 76)."""
import hashlib


def fn(args):
    """input_schema {text? , path?} -> sha256 hexdigest."""
    if args.get("path"):
        h = hashlib.sha256()
        with open(args["path"], "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return {"sha256": h.hexdigest(), "source": "file",
                "path": args["path"]}
    text = str(args.get("text") or "")
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source": "text", "length": len(text)}


def register(ctx):
    ctx.register_tool({
        "name": "plugin_sha256",
        "description": "Hash text or a file with SHA-256",
        "input_schema": {"type": "object",
                         "properties": {"text": {"type": "string"},
                                        "path": {"type": "string"}}},
        "output_schema": {"type": "object",
                          "properties": {"sha256": {"type": "string"}}},
        "permissions": [], "risk": "none", "scope": "local",
        "availability": "always", "version": "1.0.0",
        "verification": "deterministic_hash",
        "fn": fn,
    })
