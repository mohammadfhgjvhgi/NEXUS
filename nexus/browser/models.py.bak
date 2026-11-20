"""Browser Runtime models (Final Build Plan §11.1 / Spec §51–§55).

The §11.1 capability vocabulary, verbatim:

=================  =====================================================
``navigation``     goto · back · forward · reload · wait
``DOM``            read text · attributes · counts (selectors)
``forms``          fill · click · type · select · press
``upload``         set_input_files on a file input
``download``       fetch a URL to disk (or capture a download event)
``tabs``           list · select · new · close
``browser states`` session snapshots · screenshots · storage state
=================  =====================================================

The ADAPTed browser-use pattern (Round 7, zero imports): an
action-registry surface for agents — every action maps 1:1 onto a
§8.1 ``browser`` tool operation, so the vocabulary stays declarative
data, not scattered code.

مفردات المتصفح — الثمانية حرفيًا، وكل فعل خلف بوابة §8.2.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The §11.1 capability families, verbatim.
BROWSER_DOMAINS: tuple[str, ...] = (
    "navigation",
    "dom",
    "forms",
    "upload",
    "download",
    "tabs",
    "states",
    "automation",
)

#: The §8.1 tool operation vocabulary (the ``browser`` tool surface).
BROWSER_OPERATIONS: tuple[str, ...] = (
    # navigation
    "navigate",
    "back",
    "forward",
    "reload",
    "wait",
    # dom
    "read",
    # forms
    "click",
    "type",
    "fill",
    "select",
    "press",
    # upload / download
    "upload",
    "download",
    # tabs
    "tabs",
    "tab_select",
    "tab_new",
    "tab_close",
    # states
    "snapshot",
    "screenshot",
    # lifecycle
    "attach",
    "close",
)

#: Operations that only read (verification + scope classification).
READ_ONLY_OPERATIONS: frozenset[str] = frozenset(
    {"read", "tabs", "snapshot", "wait"}
)

#: Operations whose arguments carry workspace paths (§8.2 scope stage).
PATH_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "upload": ("path",),
    "download": ("path",),
    "screenshot": ("path",),
}


@dataclass(frozen=True, slots=True)
class PageSnapshot:
    """One page's observable state — what the agent sees (§ states)."""

    url: str = ""
    title: str = ""
    session_id: str = ""
    tab_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "session_id": self.session_id,
            "tab_count": self.tab_count,
            **self.extra,
        }


__all__ = [
    "BROWSER_DOMAINS",
    "BROWSER_OPERATIONS",
    "PageSnapshot",
    "PATH_ARGUMENTS",
    "READ_ONLY_OPERATIONS",
]
