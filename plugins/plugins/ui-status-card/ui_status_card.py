# -*- coding: utf-8 -*-
"""Sample UI plugin — a dashboard card contribution with a renderer."""

CARD_ID = "plugins-status-card"


def render(snapshot, lang="ar"):
    counts = snapshot.get("counts_by_type", {})
    total = snapshot.get("loaded_total", 0)
    cells = "".join(
        f"<span class=\"nx-card-cell\">{t}: {n}</span>"
        for t, n in sorted(counts.items()))
    title = "بطاقة الإضافات" if lang == "ar" else "Plugins status card"
    return (f"<div class=\"nx-card\" id=\"{CARD_ID}\">"
            f"<div class=\"nx-card-title\">{title}</div>"
            f"<div class=\"nx-card-total\">loaded={total}</div>"
            f"{cells}</div>")


def register(ctx):
    ctx.register_ui_card({
        "id": CARD_ID, "slot": "dashboard.sidebar",
        "data": "plugins-registry", "render": render, "lang": "ar",
    })
