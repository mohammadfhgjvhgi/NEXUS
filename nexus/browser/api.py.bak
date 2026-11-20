"""Browser API (Final Build Plan §11.1 — the façade).

:class:`BrowserRuntime` is the browser twin of the §9.1 Computer
API: every domain method is a **thin router client** —
``router.route("browser", ...)`` through the §8.2 seven-stage
pipeline. The Browser API adds no second choke point and no new
event names; the §10.3 input arbitration (when the harness runs)
still guards the human's windows.

The convenience surface mirrors the §11.1 vocabulary:
``navigate`` · ``read`` · ``click`` · ``type``/``fill`` (with
``vault_ref`` for §11.5) · ``upload`` · ``download`` · ``tabs`` ·
``snapshot``/``screenshot``, plus :meth:`attach_user_cdp` — the
explicit §55 gate — and :meth:`claim_new_windows` — the Phase-9
integration that stakes the agent's browser windows as NEXUS.

واجهة المتصفح — سياسة وتنسيق فوق الموجّه نفسه، ولا بوابة ثانية.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..tools.router import ToolRouter


class BrowserApiError(Exception):
    """A browser domain call failed — honest, with the trace."""


#: The §11.1 domains the façace exposes (mirror of the tool surface).
BROWSER_FACADE_DOMAINS: tuple[str, ...] = (
    "navigation", "dom", "forms", "upload", "download", "tabs", "states",
)


class BrowserRuntime:
    """The §11.1 façade over the §8.2 router (the browser tool)."""

    def __init__(
        self,
        router: ToolRouter,
        *,
        policy: Any = None,
        workspace_id: str | None = None,
        agent_id: str = "browser",
    ) -> None:
        self._router = router
        self._policy = policy
        self._workspace_id = workspace_id
        self._agent_id = agent_id
        self._active_task_id = ""

    @property
    def router(self) -> ToolRouter:
        return self._router

    def _route(
        self, arguments: Mapping[str, Any], *, task_id: str = ""
    ) -> Any:
        outcome = self._router.route(
            "browser",
            dict(arguments),
            task_id=task_id or self._active_task_id,
            agent_id=self._agent_id,
            policy=self._policy,
            workspace_id=self._workspace_id,
        )
        return outcome

    # ------------------------------------------------------------ domains

    def navigate(self, url: str, *, session: str = "agent", task_id: str = "") -> Any:
        return self._route(
            {"op": "navigate", "url": url, "session": session}, task_id=task_id
        )

    def back(self, *, session: str = "agent", task_id: str = "") -> Any:
        return self._route({"op": "back", "session": session}, task_id=task_id)

    def forward(self, *, session: str = "agent", task_id: str = "") -> Any:
        return self._route({"op": "forward", "session": session}, task_id=task_id)

    def reload(self, *, session: str = "agent", task_id: str = "") -> Any:
        return self._route({"op": "reload", "session": session}, task_id=task_id)

    def read(
        self, selector: str, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "read", "selector": selector, "session": session},
            task_id=task_id,
        )

    def click(
        self, selector: str, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "click", "selector": selector, "session": session},
            task_id=task_id,
        )

    def type(
        self,
        selector: str,
        *,
        text: str | None = None,
        vault_ref: str | None = None,
        session: str = "agent",
        task_id: str = "",
    ) -> Any:
        arguments: dict[str, Any] = {
            "op": "type",
            "selector": selector,
            "session": session,
        }
        if vault_ref is not None:
            arguments["vault_ref"] = vault_ref
        else:
            arguments["text"] = text or ""
        return self._route(arguments, task_id=task_id)

    def fill(
        self,
        selector: str,
        *,
        text: str | None = None,
        vault_ref: str | None = None,
        session: str = "agent",
        task_id: str = "",
    ) -> Any:
        arguments: dict[str, Any] = {
            "op": "fill", "selector": selector, "session": session
        }
        if vault_ref is not None:
            arguments["vault_ref"] = vault_ref
        else:
            arguments["text"] = text or ""
        return self._route(arguments, task_id=task_id)

    def select(
        self, selector: str, value: str, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "select", "selector": selector, "value": value, "session": session},
            task_id=task_id,
        )

    def press(self, key: str, *, session: str = "agent", task_id: str = "") -> Any:
        return self._route(
            {"op": "press", "key": key, "session": session}, task_id=task_id
        )

    def upload(
        self, selector: str, path: str, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "upload", "selector": selector, "path": path, "session": session},
            task_id=task_id,
        )

    def download(
        self, url: str, path: str, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "download", "url": url, "path": path, "session": session},
            task_id=task_id,
        )

    def tabs(self, *, session: str = "agent", task_id: str = "") -> Any:
        return self._route({"op": "tabs", "session": session}, task_id=task_id)

    def tab_select(
        self, index: int, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "tab_select", "index": index, "session": session},
            task_id=task_id,
        )

    def tab_new(
        self, url: str = "", *, session: str = "agent", task_id: str = ""
    ) -> Any:
        arguments: dict[str, Any] = {"op": "tab_new", "session": session}
        if url:
            arguments["url"] = url
        return self._route(arguments, task_id=task_id)

    def tab_close(
        self, index: int, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "tab_close", "index": index, "session": session},
            task_id=task_id,
        )

    def snapshot(self, *, session: str = "agent", task_id: str = "") -> Any:
        return self._route({"op": "snapshot", "session": session}, task_id=task_id)

    def screenshot(
        self, path: str, *, session: str = "agent", task_id: str = ""
    ) -> Any:
        return self._route(
            {"op": "screenshot", "path": path, "session": session},
            task_id=task_id,
        )

    # -------------------------------------------------------- the §55 gate

    def attach_user_cdp(self, cdp_url: str, *, task_id: str = "") -> Any:
        """Explicit-only CDP attach to the user's browser (§11.4/§55)."""
        return self._route(
            {"op": "attach", "cdp_url": cdp_url, "session": "user"},
            task_id=task_id,
        )

    # ------------------------------------------------------------ vault

    def vault_list(self, *, task_id: str = "") -> Any:
        return self._route({"op": "vault_list"}, task_id=task_id)

    def vault_store(
        self, site: str, username: str, secret_path: str, *, task_id: str = ""
    ) -> Any:
        return self._route(
            {
                "op": "vault_store",
                "site": site,
                "username": username,
                "secret_path": secret_path,
            },
            task_id=task_id,
        )

    def vault_forget(self, site: str, *, task_id: str = "") -> Any:
        return self._route({"op": "vault_forget", "site": site}, task_id=task_id)

    # --------------------------------------------------------- §9.5 layer

    def act(self, target: Any) -> Any:
        """The §9.5 chain seam — one ActionTarget through the DOM layer.

        Handles ``click`` · ``type`` · ``set_value`` · ``inspect``
        with ``target.name`` as the selector (``value`` as the text).
        """
        action = str(getattr(target, "action", ""))
        selector = str(target.name or "")
        value = str(target.value or "")
        if action in ("click", "invoke"):
            return self.click(selector)
        if action in ("type", "set_value"):
            if value:
                return self.fill(selector, text=value)
            raise BrowserApiError("dom layer needs a value for type/set_value")
        if action == "inspect":
            return self.read(selector)
        raise BrowserApiError(f"dom layer cannot handle action {action!r}")

    def claim_new_windows(self, window_manager: Any) -> dict[str, Any]:
        """The Phase-9 integration (§10 diff-claim of agent windows)."""
        from .engine import get_engine

        return get_engine().claim_new_windows(window_manager)

    # ------------------------------------------------------------- probes

    def capability_report(self) -> dict[str, Any]:
        registered = self._router.registry.get("browser")
        if registered is None:
            return {"browser": {"available": False, "reason": "not registered"}}
        capability = registered.capabilities()
        return {"browser": {
            "available": bool(capability.available),
            "reason": capability.reason,
        }}


__all__ = [
    "BROWSER_FACADE_DOMAINS",
    "BrowserApiError",
    "BrowserRuntime",
]
