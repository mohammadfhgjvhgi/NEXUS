"""Process-wide vision wiring state (the browser-engine precedent).

The runtime injects the §12.2 provider (over the live Model
Runtime) and the §12.5 OCR preference here; the ``vision`` tool
record reads them lazily. Defaults are honest: no provider wired,
``auto`` OCR — the tool refuses inference ops with a reason, and
capture/OCR still work as their capability allows.

حالة الربط — المزوّد يُحقن من التشغيل، والأداة تقرأها كسولة.

Stdlib only.
"""

from __future__ import annotations

from typing import Any

_provider: Any = None
_ocr_preference: str = "auto"


def set_provider(provider: Any) -> None:
    """Inject the §12.2 VisionProvider (runtime wiring)."""
    global _provider
    _provider = provider


def get_provider() -> Any:
    """The wired provider, or ``None`` (honest)."""
    return _provider


def set_ocr_preference(preference: str) -> None:
    """Pin the §12.5 engine preference (config ``vision_ocr_engine``)."""
    global _ocr_preference
    _ocr_preference = preference


def get_ocr_preference() -> str:
    return _ocr_preference


def reset() -> None:
    """Restore the honest defaults (tests + re-wiring)."""
    global _provider, _ocr_preference
    _provider = None
    _ocr_preference = "auto"


__all__ = [
    "get_ocr_preference",
    "get_provider",
    "reset",
    "set_ocr_preference",
    "set_provider",
]
