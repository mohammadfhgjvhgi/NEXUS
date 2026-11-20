"""The Playwright engine adapter (Final Build Plan §11.1 — MODE A «USE»).

microsoft/playwright (Apache-2.0, pinned via the ``[browser]`` extra)
is the **browser execution engine** — navigation · DOM · forms ·
upload · download · tabs · browser states · automation, verbatim.
NEXUS owns every policy decision; Playwright only executes.

Discipline (the pywinauto/[computer] precedent, Round 5):

* **lazy import per method** — a missing extra never breaks the
  boot; the probe reports honestly;
* one engine **singleton** per process (module-level
  :func:`get_engine`), defaults injected at wiring time;
* every op serialized behind one lock — the sync API is
  single-threaded by contract;
* the **channel ladder** — chromium → chrome → msedge: the engine
  prefers bundled Chromium but happily drives the operator's
  installed Chrome (channel="chrome") so a machine with Chrome
  needs no 150 MB download;
* the agent context is a **persistent context** in the session
  manager's isolated profile (§11.4); the user context only via
  explicit CDP attach;
* secrets enter via **vault references** resolved at this seam —
  the plaintext goes straight into the page, never back out
  (§11.5); every output passes the vault scrubber.

المحرك — Playwright خلف واجهة NEXUS، والقنوات سلمٌ، والأسرار
تُحقن هنا ولا تخرج أبدًا.

Stdlib only here (playwright is an optional pinned extra).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from .auth import BrowserVault, VaultError
from .models import PageSnapshot
from .selfheal import SelectorFallbacks, SelfHealError, resolve
from .sessions import BrowserSessionManager, SessionError

logger = logging.getLogger("nexus.browser")

#: The channel ladder — first that launches wins.
CHANNEL_LADDER: tuple[str, ...] = ("chromium", "chrome", "msedge")

#: The opening page — its title makes the agent window discoverable
#: by the §10.2 title rules ("NEXUS Agent Session").
_AGENT_HOME = "data:text/html,<title>NEXUS Agent Session</title><h1>NEXUS</h1>"

_NAV_TIMEOUT_MS = 30_000
_ACTION_TIMEOUT_MS = 15_000


class EngineError(Exception):
    """An engine op failed — honest, with the reason."""


class PlaywrightEngine:
    """The §11.1 execution engine over Playwright's sync API."""

    def __init__(
        self,
        session_manager: BrowserSessionManager,
        *,
        vault: BrowserVault | None = None,
        channel: str = "chromium",
        headless: bool = False,
        data_root: Path | str = ".nexus",
    ) -> None:
        self._sessions = session_manager
        self._vault = vault
        self._channel = channel if channel in CHANNEL_LADDER else "chromium"
        self._headless = headless
        self._data_root = Path(data_root)
        self._lock = threading.RLock()
        self._playwright: Any = None  # the sync driver
        self._contexts: dict[str, Any] = {}  # kind → BrowserContext
        self._active_channel = ""

    # ------------------------------------------------------------- probes

    @staticmethod
    def library_available() -> tuple[bool, str]:
        try:
            import playwright  # noqa: F401 — the probe is the point
        except ImportError as exc:
            return False, f"playwright extra missing ({exc})"
        return True, "playwright installed ([browser] extra)"

    def available(self) -> tuple[bool, str]:
        ok, reason = self.library_available()
        if not ok:
            return ok, reason
        with self._lock:
            if self._contexts:
                return True, (
                    f"live ({len(self._contexts)} context(s), "
                    f"channel={self._active_channel})"
                )
        return True, f"playwright ready (channel ladder {CHANNEL_LADDER})"

    @property
    def active_channel(self) -> str:
        return self._active_channel

    @property
    def vault(self) -> BrowserVault | None:
        """The §11.5 vault (tool ops touch it; secrets never return)."""
        return self._vault

    def set_defaults(self, *, channel: str, headless: bool) -> None:
        if channel in CHANNEL_LADDER:
            self._channel = channel
        self._headless = bool(headless)

    # ------------------------------------------------------------ lifecycle

    def _driver(self) -> Any:
        if self._playwright is None:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
        return self._playwright

    def ensure_agent_context(self) -> Any:
        """The §11.4 agent session — persistent, isolated, ours."""
        with self._lock:
            existing = self._contexts.get("agent")
            if existing is not None:
                return existing
            driver = self._driver()
            profile = self._sessions.agent_profile_dir
            errors: list[str] = []
            ladder = [self._channel] + [
                channel for channel in CHANNEL_LADDER if channel != self._channel
            ]
            for channel in ladder:
                try:
                    context = driver.chromium.launch_persistent_context(
                        user_data_dir=profile,
                        channel=channel if channel != "chromium" else None,
                        headless=self._headless,
                        viewport={"width": 1280, "height": 800},
                        args=["--no-first-run", "--no-default-browser-check"],
                    )
                    context.set_default_timeout(_ACTION_TIMEOUT_MS)
                    context.set_default_navigation_timeout(_NAV_TIMEOUT_MS)
                    self._contexts["agent"] = context
                    self._active_channel = channel
                    self._sessions.register(
                        "agent", engine=context, profile_dir=profile
                    )
                    if context.pages:
                        page = context.pages[0]
                    else:
                        page = context.new_page()
                    try:
                        if page.url in ("about:blank", "chrome://new-tab-page"):
                            page.goto(_AGENT_HOME)
                    except Exception:  # noqa: BLE001 — a title is cosmetic
                        pass
                    logger.info(
                        "agent browser context live (channel=%s, profile=%s)",
                        channel,
                        profile,
                    )
                    return context
                except Exception as exc:  # noqa: BLE001 — try the next rung
                    errors.append(f"{channel}: {exc}")
            raise EngineError(
                "no browser channel launched — " + " | ".join(errors[:3])
            )

    def attach_user_cdp(self, cdp_url: str) -> Any:
        """The §11.4/§55 user session — explicit consent + explicit URL."""
        cdp_url = self._sessions.request_user_cdp(cdp_url)  # the gate
        with self._lock:
            existing = self._contexts.get("user")
            if existing is not None:
                return existing
            driver = self._driver()
            try:
                browser = driver.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:  # noqa: BLE001 — honest failure
                raise EngineError(f"CDP attach failed: {exc}") from exc
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            self._contexts["user"] = context
            self._sessions.register(
                "user", engine=context, cdp_url=cdp_url
            )
            logger.info("user browser context attached over CDP (%s)", cdp_url)
            return context

    def _context_for(self, session: str) -> Any:
        if session == "user":
            if "user" not in self._contexts:
                raise EngineError(
                    "no user session — attach requires the explicit CDP "
                    "gate (op 'attach' with cdp_url)"
                )
            return self._contexts["user"]
        return self.ensure_agent_context()

    def _page_for(self, session: str, index: int | None = None) -> Any:
        context = self._context_for(session)
        pages = [page for page in context.pages if not _is_cruft(page)]
        if not pages:
            page = context.new_page()
            if session == "agent":
                try:
                    page.goto(_AGENT_HOME)
                except Exception:  # noqa: BLE001 — cosmetic
                    pass
            return page
        if index is None:
            return context.pages[-1]
        if not 0 <= index < len(context.pages):
            raise EngineError(
                f"tab index {index} out of range (have {len(context.pages)})"
            )
        return context.pages[index]

    def shutdown(self) -> None:
        """Close every context + stop the driver (idempotent)."""
        with self._lock:
            for context in self._contexts.values():
                try:
                    context.close()
                except Exception:  # noqa: BLE001 — teardown never raises
                    logger.exception("context close error — logged")
            self._contexts.clear()
            self._sessions.close_all()
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:  # noqa: BLE001
                    logger.exception("driver stop error — logged")
                self._playwright = None

    # ---------------------------------------------------------------- ops

    def op(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """One §11.1 operation — the tool handler's single seam."""
        with self._lock:
            handler = getattr(self, f"_op_{operation}", None)
            if handler is None:
                raise EngineError(f"unknown browser op {operation!r}")
            result = handler(arguments)
            return self._scrub(result if result is not None else {})

    # ---- navigation

    def _op_navigate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = str(arguments.get("url", ""))
        if not url:
            raise EngineError("navigate requires a url")
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        response = page.goto(url)
        return _snapshot(page, session).to_dict() | {
            "status": getattr(response, "status", None),
        }

    def _op_back(self, arguments: dict[str, Any]) -> dict[str, Any]:
        page = self._page_for(str(arguments.get("session", "agent")))
        page.go_back()
        return _snapshot(page, "agent").to_dict()

    def _op_forward(self, arguments: dict[str, Any]) -> dict[str, Any]:
        page = self._page_for(str(arguments.get("session", "agent")))
        page.go_forward()
        return _snapshot(page, "agent").to_dict()

    def _op_reload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        page = self._page_for(str(arguments.get("session", "agent")))
        page.reload()
        return _snapshot(page, "agent").to_dict()

    def _op_wait(self, arguments: dict[str, Any]) -> dict[str, Any]:
        milliseconds = int(arguments.get("ms", 1000))
        page = self._page_for(str(arguments.get("session", "agent")))
        page.wait_for_load_state("load", timeout=milliseconds + 5_000)
        page.wait_for_timeout(milliseconds)
        return {"waited_ms": milliseconds}

    # ---- dom

    def _op_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        spec = SelectorFallbacks.parse(str(arguments.get("selector", "body")))
        locator = resolve(page, spec)
        text = locator.inner_text() if _count(locator) else ""
        return {
            "selector": str(arguments.get("selector", "body")),
            "count": _count(locator),
            "text": (text or "")[:4000],
            "url": page.url,
            "title": page.title(),
        }

    # ---- forms

    def _type_value(self, arguments: dict[str, Any]) -> str:
        vault_ref = arguments.get("vault_ref")
        if vault_ref:
            if self._vault is None:
                raise VaultError("no vault configured for this engine")
            _username, secret = self._vault.issue(str(vault_ref))
            return secret  # typed straight into the page — never returned
        text = arguments.get("text")
        if text is None:
            raise EngineError("forms ops require text or vault_ref")
        return str(text)

    def _op_click(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        spec = SelectorFallbacks.parse(str(arguments.get("selector", "")))
        if not spec.candidates():
            raise EngineError("click requires a selector")
        locator = resolve(page, spec)
        locator.click()
        return {"clicked": arguments.get("selector"), **_snapshot(page, session).to_dict()}

    def _op_type(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        spec = SelectorFallbacks.parse(str(arguments.get("selector", "")))
        if not spec.candidates():
            raise EngineError("type requires a selector")
        value = self._type_value(arguments)
        locator = resolve(page, spec)
        locator.type(value, delay=15)
        # the response never carries the value (§11.5) — only the fact
        return {"typed": True, "secret": bool(arguments.get("vault_ref")),
                **_snapshot(page, session).to_dict()}

    def _op_fill(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        spec = SelectorFallbacks.parse(str(arguments.get("selector", "")))
        if not spec.candidates():
            raise EngineError("fill requires a selector")
        value = self._type_value(arguments)
        locator = resolve(page, spec)
        locator.fill(value)
        return {"filled": True, "secret": bool(arguments.get("vault_ref")),
                **_snapshot(page, session).to_dict()}

    def _op_select(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        spec = SelectorFallbacks.parse(str(arguments.get("selector", "")))
        value = str(arguments.get("value", ""))
        locator = resolve(page, spec)
        locator.select_option(value)
        return {"selected": value, **_snapshot(page, session).to_dict()}

    def _op_press(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        key = str(arguments.get("key", "Enter"))
        page.keyboard.press(key)
        return {"pressed": key}

    # ---- upload / download

    def _op_upload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        path = str(arguments.get("path", ""))
        if not path:
            raise EngineError("upload requires a path")
        source = Path(path)
        if not source.is_file():
            raise EngineError(f"upload source missing: {path}")
        page = self._page_for(session)
        spec = SelectorFallbacks.parse(str(arguments.get("selector", "input[type=file]")))
        locator = resolve(page, spec)
        locator.set_input_files(str(source))
        return {"uploaded": str(source), "bytes": source.stat().st_size}

    def _op_download(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        url = str(arguments.get("url", ""))
        path = str(arguments.get("path", ""))
        if not url or not path:
            raise EngineError("download requires url and path")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if url.startswith("file://"):
            # the request API is http(s)-only — a file:// target is an
            # honest local copy (same receipt, no network pretense)
            source = Path(url[7:])
            for drive in ("C", "D", "E", "F"):
                if url.startswith(f"file:///{drive}:/") or url.startswith(
                    f"file:///{drive.lower()}:/"
                ):
                    source = Path(f"{drive}:\\" + url.split(":/", 1)[1])
                    break
            if not source.is_file():
                raise EngineError(f"download source missing: {url}")
            body = source.read_bytes()
            target.write_bytes(body)
            return {"downloaded": str(target), "bytes": len(body), "url": url}
        context = self._context_for(session)
        response = context.request.get(url)
        if not response.ok:
            raise EngineError(f"download failed: HTTP {response.status}")
        body = response.body()
        target.write_bytes(body)
        return {"downloaded": str(target), "bytes": len(body), "url": url}

    # ---- tabs

    def _op_tabs(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        context = self._context_for(session)
        rows = []
        for index, page in enumerate(context.pages):
            rows.append(
                {
                    "index": index,
                    "url": page.url[:200],
                    "title": (page.title() or "")[:120],
                }
            )
        return {"tabs": rows, "count": len(rows), "session": session}

    def _op_tab_select(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        index = int(arguments.get("index", 0))
        page = self._page_for(session, index)
        page.bring_to_front()
        return _snapshot(page, session).to_dict()

    def _op_tab_new(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        context = self._context_for(session)
        page = context.new_page()
        url = arguments.get("url")
        if url:
            page.goto(str(url))
        return _snapshot(page, session).to_dict()

    def _op_tab_close(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        context = self._context_for(session)
        index = int(arguments.get("index", len(context.pages) - 1))
        if not 0 <= index < len(context.pages):
            raise EngineError(f"tab index {index} out of range")
        context.pages[index].close()
        return {"closed": index, "count": len(context.pages)}

    # ---- states

    def _op_snapshot(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        page = self._page_for(session)
        return _snapshot(page, session).to_dict()

    def _op_screenshot(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        path = str(arguments.get("path", ""))
        if not path:
            raise EngineError("screenshot requires a path")
        page = self._page_for(session)
        page.screenshot(path=path)
        size = Path(path).stat().st_size
        return {"screenshot": path, "bytes": size}

    def _op_close(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = str(arguments.get("session", "agent"))
        context = self._contexts.pop(session, None)
        if context is None:
            return {"closed": False, "session": session}
        context.close()
        session_row = (
            self._sessions.agent_session()
            if session == "agent"
            else self._sessions.user_session()
        )
        if session_row is not None:
            self._sessions.close(session_row.session_id)
        return {"closed": True, "session": session}

    def _op_attach(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cdp_url = str(arguments.get("cdp_url", ""))
        context = self.attach_user_cdp(cdp_url)
        return {"attached": cdp_url, "pages": len(context.pages)}

    # ------------------------------------------------------------ secrets

    def _scrub(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The §11.5 last line — no known secret survives an output."""
        if self._vault is None:
            return payload
        secrets = self._vault.known_secrets()
        if not secrets:
            return payload
        for key, value in list(payload.items()):
            if isinstance(value, str):
                for secret in secrets:
                    if secret and secret in value:
                        payload[key] = value.replace(secret, "[REDACTED]")
        return payload

    def claim_new_windows(self, window_manager: Any) -> dict[str, Any]:
        """Phase 9 integration — the §10 diff-claim.

        Sync the §10 window registry before/after the agent context
        exists; every *new* browser window is an agent window —
        claim it as NEXUS so the input arbitration guards the human's
        Chrome while the agent works in its own.
        """
        before = set()
        try:
            window_manager.sync()
            before = {record.window_id for record in window_manager.registry.records()}
        except Exception:  # noqa: BLE001 — §10 is optional here
            return {"claimed": 0, "reason": "window manager unavailable"}
        self.ensure_agent_context()
        import time

        time.sleep(1.0)  # let the window appear
        window_manager.sync()
        new_ids = [
            record.window_id
            for record in window_manager.registry.records()
            if record.window_id not in before
        ]
        for window_id in new_ids:
            window_manager.claim(window_id, owner="NEXUS", agent="browser-runtime")
        return {"claimed": len(new_ids), "windows": new_ids}


# ------------------------------------------------------------- singleton

_ENGINE: PlaywrightEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_engine(
    data_root: Path | str = ".nexus",
) -> PlaywrightEngine:
    """The process-wide engine (defaults overridable at wiring time)."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            root = Path(data_root)
            sessions = BrowserSessionManager(root)
            vault = BrowserVault(root)
            _ENGINE = PlaywrightEngine(
                sessions, vault=vault, data_root=root
            )
        return _ENGINE


def set_engine_defaults(
    *,
    channel: str,
    headless: bool,
    data_root: Path | str,
    user_consent: bool = False,
) -> None:
    """Runtime wiring injects the config before any first use.

    An engine with no live contexts may be *re-created* with a new
    data root (test isolation); a live engine keeps its sessions and
    only the channel/headless knobs move.
    """
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None or not _ENGINE._contexts:
            root = Path(data_root)
            sessions = BrowserSessionManager(root, user_consent=user_consent)
            vault = BrowserVault(root)
            _ENGINE = PlaywrightEngine(
                sessions, vault=vault, channel=channel, headless=headless,
                data_root=root,
            )
        else:
            _ENGINE.set_defaults(channel=channel, headless=headless)


def _snapshot(page: Any, session: str) -> PageSnapshot:
    try:
        title = page.title()
    except Exception:  # noqa: BLE001 — a dying tab has no title
        title = ""
    return PageSnapshot(
        url=str(page.url)[:500],
        title=title[:200],
        session_id=session,
        tab_count=len(page.context.pages),
    )


def _count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:  # noqa: BLE001 — fakes may not implement count
        return 1


def _is_cruft(page: Any) -> bool:
    """Chrome's own helper targets never count as tabs."""
    try:
        return str(page.url).startswith(("devtools://", "chrome-extension://"))
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "CHANNEL_LADDER",
    "EngineError",
    "PlaywrightEngine",
    "get_engine",
    "set_engine_defaults",
    "SessionError",
    "SelfHealError",
]
