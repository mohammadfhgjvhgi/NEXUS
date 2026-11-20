"""Browser Sessions (Final Build Plan §11.4 / Spec §55).

The human-parallelism rule, browser edition (Spec §55):

    المستخدم يعمل في Chrome · NEXUS يعمل في Session أخرى —
    ولا تختلط الـCookies والسياقات إلا عند الحاجة الصريحة.

:class:`BrowserSessionManager` enforces it structurally:

* **AGENT session** — NEXUS's own browser: a persistent context
  (launch_persistent_context) rooted at its own profile directory
  under ``NexusPaths.data`` — *never* the user's Chrome profile.
  Persistence is what browser-use calls persistent workflows
  (§11.2): cookies · localStorage survive across runs.
* **USER session** — CDP attach to the *user's* running Chrome
  (``connect_over_cdp``), **explicit opt-in only**: the endpoint
  must be provided and the consent flag set. Without it, every
  user-session request refuses honestly — the default never mixes.

Every session carries an id that rides tool calls and events (never
credentials — those live in :mod:`nexus.browser.auth`).

جلسات المتصفح — الوكيل ببروفايله المعزول، والمستخدم عبر CDP
بتصرّح صريح فقط، والخلط استثناء موثّق لا افتراض.

Stdlib only (the engine adapts Playwright lazily — MODE A).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("nexus.browser")

#: The §11.4 session kinds, verbatim.
SESSION_KINDS: tuple[str, ...] = ("user", "agent")

#: The §55 explicit-consent flag name (documented, single switch).
USER_SESSION_CONSENT_KEY = "browser.user_session_cdp"


class SessionError(Exception):
    """A session lifecycle violation — honest, with the reason."""


@dataclass(slots=True)
class BrowserSession:
    """One live browser session — kind · identity · isolation facts."""

    session_id: str
    kind: str  # "user" | "agent"
    profile_dir: str = ""
    cdp_url: str = ""
    created_at: str = ""
    engine: Any = None  # the Playwright context (opaque to this layer)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def is_agent(self) -> bool:
        return self.kind == "agent"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "kind": self.kind,
            "profile_dir": self.profile_dir,
            "cdp_url": self.cdp_url,
            "created_at": self.created_at,
        }


class BrowserSessionManager:
    """Owns the session registry + the isolation invariant.

    The manager does not drive the browser (the engine does); it
    decides *who* may run *where*, and keeps the two worlds apart:

    * the agent profile directory is fixed and private
      (``<data>/browser/agent-profile``) — it cannot be pointed at
      the user's real Chrome profile (refused on construction);
    * the user session exists only via :meth:`user_session` with an
      explicit ``cdp_url`` — there is no default, no discovery, no
      silent attach;
    * :meth:`get` / :meth:`snapshot` answer per session_id, so tool
      calls and events can be tagged without ever touching
      credentials.
    """

    def __init__(self, data_root: Path | str, *, user_consent: bool = False) -> None:
        self._root = Path(data_root)
        self._agent_profile = (self._root / "browser" / "agent-profile").resolve()
        self._user_consent = bool(user_consent)
        self._sessions: dict[str, BrowserSession] = {}
        self._counter = 0

    # ------------------------------------------------------------ registry

    @property
    def agent_profile_dir(self) -> str:
        """The one fixed agent profile root (isolated by construction)."""
        (self._agent_profile).mkdir(parents=True, exist_ok=True)
        return str(self._agent_profile)

    def guard_profile(self, profile_dir: str) -> str:
        """Refuse any profile that points at (or inside) a user-like
        Chrome profile — the §11.4 mixing guard, structural."""
        from pathlib import PureWindowsPath

        normalized = str(Path(profile_dir)).replace("\\", "/").lower()
        for marker in (
            "/appdata/local/google/chrome/user data",
            "/appdata/roaming/mozilla/firefox",
            "/appdata/local/microsoft/edge/user data",
            "/library/application support/google/chrome",
        ):
            if marker in normalized:
                raise SessionError(
                    f"refusing user browser profile {profile_dir!r} — "
                    "agent sessions must stay isolated (Spec §55)"
                )
        # the agent profile itself is always allowed
        if PureWindowsPath(normalized) == PureWindowsPath(
            str(self._agent_profile).replace("\\", "/").lower()
        ):
            return str(self._agent_profile)
        return profile_dir

    def new_session_id(self, kind: str) -> str:
        if kind not in SESSION_KINDS:
            raise SessionError(f"kind must be one of {SESSION_KINDS}, got {kind!r}")
        self._counter += 1
        return f"browser-{kind}-{self._counter:04d}"

    def register(
        self,
        kind: str,
        *,
        engine: Any,
        profile_dir: str = "",
        cdp_url: str = "",
    ) -> BrowserSession:
        session = BrowserSession(
            session_id=self.new_session_id(kind),
            kind=kind,
            profile_dir=profile_dir,
            cdp_url=cdp_url,
            created_at=_utc_now_iso(),
            engine=engine,
        )
        self._sessions[session.session_id] = session
        logger.info("browser session opened: %s", session.to_dict())
        return session

    def get(self, session_id: str) -> BrowserSession | None:
        return self._sessions.get(session_id)

    def agent_session(self) -> BrowserSession | None:
        for session in self._sessions.values():
            if session.is_agent:
                return session
        return None

    def user_session(self) -> BrowserSession | None:
        for session in self._sessions.values():
            if session.kind == "user":
                return session
        return None

    def close(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        try:
            engine = session.engine
            if engine is not None and hasattr(engine, "close"):
                engine.close()
        except Exception:  # noqa: BLE001 — teardown never raises outward
            logger.exception("session close error (%s) — logged", session_id)
        logger.info("browser session closed: %s", session_id)
        return True

    def close_all(self) -> None:
        for session_id in list(self._sessions):
            self.close(session_id)

    # ------------------------------------------------------------ consent

    def request_user_cdp(self, cdp_url: str) -> str:
        """The §55 gate: explicit URL + explicit consent, or refuse."""
        if not self._user_consent:
            raise SessionError(
                "user-session attach requires explicit operator consent "
                f"({USER_SESSION_CONSENT_KEY}) — the default never mixes "
                "user and agent contexts (Spec §55)"
            )
        if not cdp_url or not cdp_url.startswith("http"):
            raise SessionError(
                "a CDP endpoint (http://host:port) must be provided "
                "explicitly — there is no discovery"
            )
        return cdp_url

    def snapshot(self) -> dict[str, Any]:
        return {
            "sessions": [session.to_dict() for session in self._sessions.values()],
            "count": len(self._sessions),
            "user_consent": self._user_consent,
            "agent_profile_dir": str(self._agent_profile),
        }


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


__all__ = [
    "BrowserSession",
    "BrowserSessionManager",
    "SESSION_KINDS",
    "SessionError",
    "USER_SESSION_CONSENT_KEY",
]
