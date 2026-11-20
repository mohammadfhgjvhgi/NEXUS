"""Self-healing selectors (Final Build Plan §11.3 — ADAPT from
browser-use/browser-harness, Round 7).

Browser-harness describes itself as a *thin editable CDP harness*
with **self-healing behavior** — a selector that stops matching
should not kill the task. NEXUS adapts the essence (zero imports,
the §0.5 rule holds):

* :class:`SelectorFallbacks` — one logical element, several ways to
  find it: CSS → text → role → test-id. Each candidate is tried in
  order; the **first match wins**.
* every attempt is recorded in a ledger — the honest-trace
  discipline the whole platform runs on;
* all-fail raises :class:`SelfHealError` **carrying the ledger**
  (never a bare "not found");
* bounded retries with a tiny settle wait — the harness's
  "self-healing" without an unbounded loop.

The editable-helpers seam (the agent writing helpers when a
capability is missing) maps onto the Phase-6 skill library —
documented, not duplicated here.

الشفاء الذاتي — بدائل مرتّبة وسجلّ محاولات صادق، والفشل الكامل
يرفع الخطأ حاملًا الدليل كاملًا.

Stdlib only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

#: The fallback strategy order (browser-harness's healing ladder).
STRATEGY_ORDER: tuple[str, ...] = ("css", "role", "text", "test_id")


@dataclass(frozen=True, slots=True)
class SelectorFallbacks:
    """One element, several finders — order is the healing ladder."""

    css: str = ""
    role: str = ""
    text: str = ""
    test_id: str = ""
    #: bounded retries (each retry re-runs the whole ladder)
    retries: int = 2
    #: settle wait between retries, seconds
    settle: float = 0.4

    def candidates(self) -> tuple[tuple[str, str], ...]:
        """(strategy, value) pairs in healing order — data, not code."""
        pairs = [
            ("css", self.css),
            ("role", self.role),
            ("text", self.text),
            ("test_id", self.test_id),
        ]
        return tuple((kind, value) for kind, value in pairs if value)

    @classmethod
    def parse(cls, spec: str) -> SelectorFallbacks:
        """Parse ``css=...; role=...; text=...; test_id=...`` specs."""
        kwargs: dict[str, str] = {}
        for chunk in spec.split(";"):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            key = key.strip().lower().replace("-", "_")
            if key in ("css", "role", "text", "test_id"):
                kwargs[key] = value.strip()
        if not kwargs:
            if "=" in spec:
                # only unknown keys — no candidates (refuse honestly)
                return cls()
            # a bare spec is a css selector (the common case)
            return cls(css=spec.strip())
        return cls(**kwargs)  # type: ignore[arg-type]


@dataclass(slots=True)
class HealLedger:
    """The recorded attempts — one per strategy per retry."""

    attempts: list[dict[str, str]] = field(default_factory=list)

    def record(self, strategy: str, value: str, outcome: str, detail: str = "") -> None:
        self.attempts.append(
            {
                "strategy": strategy,
                "value": value[:80],
                "outcome": outcome,
                "detail": detail[:120],
            }
        )

    def to_dict(self) -> list[dict[str, str]]:
        return list(self.attempts)


class SelfHealError(Exception):
    """The whole ladder failed — with the full ledger attached."""

    def __init__(self, message: str, ledger: HealLedger) -> None:
        super().__init__(message)
        self.ledger = ledger


def resolve(
    page: Any,
    fallbacks: SelectorFallbacks,
    *,
    finder: Any | None = None,
) -> Any:
    """Run the healing ladder against one page.

    ``finder`` overrides the playwright locator construction (tests
    inject a fake); the default expects a sync-API ``Page`` with
    ``get_by_role`` / ``get_by_text`` / ``get_by_test_id`` /
    ``locator``. The first located element wins; a located element
    that fails :meth:`count` counts as a miss and the ladder moves
    on (that *is* the healing).
    """
    ledger = HealLedger()
    last_error = ""
    for attempt in range(fallbacks.retries + 1):
        for strategy, value in fallbacks.candidates():
            try:
                locator = _locate(page, strategy, value, finder)
                if _count(locator) > 0:
                    ledger.record(strategy, value, "matched", f"try={attempt + 1}")
                    return locator
                ledger.record(strategy, value, "miss", "count=0")
            except Exception as exc:  # noqa: BLE001 — one bad strategy never kills the ladder
                last_error = str(exc)[:120]
                ledger.record(strategy, value, "error", last_error)
        if attempt < fallbacks.retries:
            time.sleep(fallbacks.settle)
    raise SelfHealError(
        f"selector ladder exhausted ({last_error or 'no match'})",
        ledger,
    )


def _locate(
    page: Any, strategy: str, value: str, finder: Any | None
) -> Any:
    if finder is not None:
        return finder(strategy, value)  # type: ignore[call-expr]
    if strategy == "css":
        return page.locator(value)  # type: ignore[attr-defined]
    if strategy == "role":
        role, _, name = value.partition(":")
        return page.get_by_role(role.strip(), name=name.strip() or None)  # type: ignore[attr-defined]
    if strategy == "text":
        return page.get_by_text(value, exact=False)  # type: ignore[attr-defined]
    return page.get_by_test_id(value)  # type: ignore[attr-defined]


def _count(locator: Any) -> int:
    try:
        return int(locator.count())  # type: ignore[attr-defined]
    except TypeError:
        return 1


__all__ = [
    "HealLedger",
    "STRATEGY_ORDER",
    "SelfHealError",
    "SelectorFallbacks",
    "resolve",
]
