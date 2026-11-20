"""Browser Runtime (Final Build Plan §11 — Playwright · browser-use ·
browser-harness, Repository Round 7).

* :mod:`nexus.browser.models`    — the §11.1 vocabulary (data, not code)
* :mod:`nexus.browser.sessions`  — §11.4 user/agent isolation (ADAPT:
                                    browser-use session/profile split)
* :mod:`nexus.browser.auth`      — §11.5 DPAPI vault + redaction (the
                                    secret never crosses the tool seam)
* :mod:`nexus.browser.engine`    — §11.1 Playwright adapter (MODE A
                                    «USE», [browser] extra, lazy)
* :mod:`nexus.browser.selfheal`  — §11.3 selector ladder (ADAPT:
                                    browser-harness self-healing)
* :mod:`nexus.browser.api`       — the façade over the §8.2 router

The §9.5 chain gains its **dom_a11y** layer: browser-capable targets
resolve before vision/input ever fire. Sessions stay isolated by
construction; credentials ride vault references, never arguments.

زمن تشغيل المتصفح — المحرك خلف الموجّه، والجلستان منفصلتان،
 والأسرار لا تعبر واجهة الأداة.

Stdlib only at the core (playwright is a MODE A pinned extra).
"""

from __future__ import annotations

from .api import BrowserApiError, BrowserRuntime
from .auth import REDACTED, BrowserVault, VaultError, redact_text
from .engine import (
    CHANNEL_LADDER,
    EngineError,
    PlaywrightEngine,
    get_engine,
    set_engine_defaults,
)
from .models import (
    BROWSER_DOMAINS,
    BROWSER_OPERATIONS,
    PATH_ARGUMENTS,
    READ_ONLY_OPERATIONS,
    PageSnapshot,
)
from .selfheal import (
    HealLedger,
    SelectorFallbacks,
    SelfHealError,
    resolve,
)
from .sessions import (
    SESSION_KINDS,
    USER_SESSION_CONSENT_KEY,
    BrowserSession,
    BrowserSessionManager,
    SessionError,
)
from .tools import BROWSER_TOOL_NAMES, BrowserDomLayer, register_browser_tools

#: The §11 sections this package implements, verbatim.
BROWSER_SECTIONS: tuple[str, ...] = (
    "engine",       # §11.1 Playwright (USE)
    "agent-layer",  # §11.2 browser-use (ADAPT)
    "selfheal",     # §11.3 browser-harness (ADAPT)
    "sessions",     # §11.4 user / agent isolation
    "auth",         # §11.5 the DPAPI vault
)

__all__ = [
    "BROWSER_SECTIONS",
    # §11.1
    "BROWSER_DOMAINS",
    "BROWSER_OPERATIONS",
    "CHANNEL_LADDER",
    "EngineError",
    "PageSnapshot",
    "PATH_ARGUMENTS",
    "READ_ONLY_OPERATIONS",
    "PlaywrightEngine",
    "get_engine",
    "set_engine_defaults",
    # §11.2/§11.4
    "SESSION_KINDS",
    "USER_SESSION_CONSENT_KEY",
    "BrowserSession",
    "BrowserSessionManager",
    "SessionError",
    # §11.3
    "HealLedger",
    "SelfHealError",
    "SelectorFallbacks",
    "resolve",
    # §11.5
    "BrowserVault",
    "REDACTED",
    "VaultError",
    "redact_text",
    # façade
    "BrowserApiError",
    "BrowserRuntime",
    "BROWSER_TOOL_NAMES",
    "BrowserDomLayer",
    "register_browser_tools",
]
