# -*- coding: utf-8 -*-
"""Sample SKILL plugin — reusable workflow template (spec 82)."""
TEMPLATE = ("لخص النص التالي في {{count}} نقاط مع الحفاظ على المصطلحات:\n\n"
            "{{text}}")


def render(inputs):
    n = int(inputs.get("count") or 4)
    return TEMPLATE.replace("{{count}}", str(n)).replace(
        "{{text}}", str(inputs.get("text") or ""))


def register(ctx):
    ctx.register_skill({
        "id": "summarize",
        "description": "Summarize text into N bullet points",
        "inputs": ["text", "count"],
        "tools": [], "workflow": ["render_prompt"],
        "verification": "prompt_contains_markers",
        "version": "1.0.0",
        "render": render,
    })
