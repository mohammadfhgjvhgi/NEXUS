"""Native tool: ``browser`` (Final Build Plan §11.1 — the §8.1 record).

The browser surface behind the §8.2 choke point — every operation
from the §11.1 vocabulary (navigation · dom · forms · upload ·
download · tabs · states) plus the §11.5 vault bookkeeping ops.
Execution lives in :mod:`nexus.browser.engine` (Playwright, MODE A
«USE», lazy); this record is policy: risk 2, scope-checked paths
(upload source · download target · screenshot target · the secret
file), honest platform/library probes, per-op verification.

The vault ops are deliberately narrow: ``vault_list`` shows site +
username only; ``vault_store``/``vault_store_env`` take a *path* or
an *env-var name* — the secret itself never crosses the arguments,
so the ``tool.called`` events stay clean by construction (§11.5).

Risk: 2 — browser control, reversible by closing the context.

Stdlib only at this layer (playwright is the optional extra).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..models import (
    CapabilityReport,
    ScopeRequirements,
    ToolCallResult,
    ToolDefinition,
    VerificationSpec,
)
from ..models import VerificationStrategy as V
from .base import (
    NativeTool,
    ToolArgError,
    object_schema,
    optional_str,
    output_schema,
    require_int,
    require_operation,
    require_str,
)

#: The §11.1 engine operations + the §11.5 vault bookkeeping.
_OPERATIONS: tuple[str, ...] = (
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
    # transfer
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
    # §11.5 vault bookkeeping (secrets never cross the arguments)
    "vault_list",
    "vault_store",
    "vault_store_env",
    "vault_forget",
)

_MUTATING: frozenset[str] = frozenset(
    {
        "navigate", "back", "forward", "reload",
        "click", "type", "fill", "select", "press",
        "upload", "download",
        "tab_select", "tab_new", "tab_close",
        "screenshot", "attach", "close",
        "vault_store", "vault_store_env", "vault_forget",
    }
)

_PATH_OPS: frozenset[str] = frozenset(
    {"upload", "download", "screenshot", "vault_store"}
)


def _engine():
    """The engine singleton (defaults injected by the runtime)."""
    from ...browser.engine import get_engine

    return get_engine()


class BrowserTool(NativeTool):
    """§11.1 ``browser`` — Playwright execution behind the router, risk 2."""

    name = "browser"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:browser",
            name=self.name,
            description=(
                "Browser capability (Playwright behind the router): "
                "navigate/back/forward/reload/wait, read(selector), "
                "click/type/fill/select/press (text or vault_ref — "
                "secrets never cross the arguments), upload(path), "
                "download(url, path), tabs/tab_select/tab_new/tab_close, "
                "snapshot, screenshot(path), attach(cdp_url), close, "
                "vault_list/vault_store/vault_store_env/vault_forget."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "session": {
                        "type": "string", "enum": ["agent", "user"],
                        "description": "§11.4 session kind (default agent)",
                    },
                    "url": {"type": "string"},
                    "selector": {
                        "type": "string",
                        "description": "css or css=..;role=..;text=..;test_id=..",
                    },
                    "text": {"type": "string"},
                    "vault_ref": {
                        "type": "string",
                        "description": "§11.5 vault site — typed, never echoed",
                    },
                    "value": {"type": "string"},
                    "key": {"type": "string"},
                    "index": {"type": "integer"},
                    "ms": {"type": "integer"},
                    "path": {"type": "string", "description": "upload/download/screenshot path"},
                    "cdp_url": {"type": "string", "description": "explicit §55 gate"},
                    "site": {"type": "string"},
                    "username": {"type": "string"},
                    "secret_path": {"type": "string", "description": "secret file (scope-checked)"},
                    "env_var": {"type": "string"},
                },
                required=("op",),
            ),
            output_schema=output_schema("page snapshot / dom text / transfer receipt / tabs"),
            permissions=("browser.control",),
            scope_requirements=ScopeRequirements(
                path_arguments=("path", "secret_path"),
                mutating_operations=tuple(
                    op for op in _OPERATIONS if op in _MUTATING
                ),
                dimensions=("network", "display"),
            ),
            risk=2,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        # JSON_FIELD contracts bind to artifact keys the handler
        # ALWAYS emits (truthy invariants) — the Verify stage flips
        # outcomes whose contract names a missing key.
        contracts: dict[str, tuple[str, str]] = {
            "navigate": ("json_field", "url"),
            "back": ("json_field", "url"),
            "forward": ("json_field", "url"),
            "reload": ("json_field", "url"),
            "wait": ("json_field", "waited_ms"),
            "read": ("json_field", "url"),
            "click": ("json_field", "clicked"),
            "type": ("json_field", "typed"),
            "fill": ("json_field", "filled"),
            "select": ("json_field", "selected"),
            "press": ("json_field", "pressed"),
            "upload": ("json_field", "uploaded"),
            "download": ("path_size", ""),
            "tabs": ("json_field", "tabs"),
            "tab_select": ("json_field", "url"),
            "tab_new": ("json_field", "url"),
            "tab_close": ("json_field", "closed"),
            "snapshot": ("json_field", "url"),
            "screenshot": ("path_size", ""),
            "attach": ("json_field", "attached"),
            "close": ("json_field", "closed"),
            "vault_list": ("json_field", "listed"),
            "vault_store": ("json_field", "stored"),
            "vault_store_env": ("json_field", "stored"),
            "vault_forget": ("json_field", "site"),
        }
        strategy, argument = contracts.get(operation, ("none", ""))
        return VerificationSpec(getattr(V, strategy.upper()), argument)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        engine = _engine()

        # ---- the §11.5 vault bookkeeping (never a secret in flight) ----
        if operation == "vault_list":
            vault = engine.vault
            entries = vault.list() if vault is not None else []
            return ToolCallResult(
                output=f"{len(entries)} vault entr{'y' if len(entries) == 1 else 'ies'}",
                artifacts={"entries": entries, "count": len(entries), "listed": True},
            )
        if operation in ("vault_store", "vault_store_env"):
            vault = engine.vault
            if vault is None:
                raise ToolArgError("op", "no vault configured")
            site = require_str(arguments, "site")
            username = require_str(arguments, "username")
            if operation == "vault_store":
                secret_path = require_str(arguments, "secret_path")
                record = vault.store_from_file(site, username, secret_path)
            else:
                env_var = require_str(arguments, "env_var")
                record = vault.store_from_env(site, username, env_var)
            return ToolCallResult(
                output=f"vault entry stored: {site} ({username})",
                artifacts={"stored": record},
            )
        if operation == "vault_forget":
            vault = engine.vault
            if vault is None:
                raise ToolArgError("op", "no vault configured")
            site = require_str(arguments, "site")
            removed = vault.forget(site)
            return ToolCallResult(
                output=f"vault forget {site}: {'ok' if removed else 'absent'}",
                artifacts={"forgotten": removed, "site": site},
            )

        # ---- the §11.1 engine operations --------------------------------
        payload: dict[str, Any] = {"op": operation}
        session = arguments.get("session", "agent")
        if session not in ("agent", "user"):
            raise ToolArgError("session", "must be 'agent' or 'user' (§11.4)")
        payload["session"] = str(session)
        for key in (
            "url", "selector", "text", "vault_ref", "value", "key",
            "path", "cdp_url", "site",
        ):
            value = optional_str(arguments, key)
            if value is not None:
                payload[key] = value
        for key in ("index", "ms"):
            if key in arguments:
                payload[key] = require_int(
                    arguments, key, default=0, low=0, high=1 << 20
                )

        # the §11.4/§55 gate: user sessions attach explicitly or refuse
        if session == "user" and operation not in ("attach",):
            if "user" not in getattr(engine, "_contexts", {}):
                raise ToolArgError(
                    "session",
                    "no user session — the §55 gate requires an explicit "
                    "attach(cdp_url) first (agent/user never mix by default)",
                )

        result = engine.op(operation, payload)
        # snapshot/tab receipts get their canonical artifact names
        artifacts: dict[str, Any] = dict(result)
        if operation == "download":
            # the PATH_SIZE contract binds to the canonical "path" key
            artifacts["path"] = result.get("downloaded", "")
        elif operation == "screenshot":
            artifacts["path"] = result.get("screenshot", "")
        if operation == "tabs":
            artifacts["tabs"] = result.get("tabs", [])
        elif operation == "read":
            artifacts["text"] = result.get("text", "")
        return ToolCallResult(
            output=_summarize(operation, artifacts),
            artifacts=artifacts,
        )

    def capabilities(self) -> CapabilityReport:
        from ...browser.engine import PlaywrightEngine

        ok, reason = PlaywrightEngine.library_available()
        if ok:
            ok, reason = self._engine_probe()
        return CapabilityReport(available=ok, reason=reason)

    @staticmethod
    def _engine_probe() -> tuple[bool, str]:
        try:
            engine = _engine()
            return engine.available()
        except Exception as exc:  # noqa: BLE001 — the probe never crashes
            return False, f"engine probe failed: {exc}"


def _summarize(operation: str, artifacts: Mapping[str, Any]) -> str:
    if operation == "navigate":
        return f"navigated → {artifacts.get('url', '')} ({artifacts.get('title', '')})"
    if operation == "read":
        return f"read {artifacts.get('count', 0)} match(es): {str(artifacts.get('text', ''))[:120]}"
    if operation == "tabs":
        return f"{artifacts.get('count', 0)} tab(s)"
    if operation == "download":
        return f"downloaded {artifacts.get('bytes', 0)} bytes → {artifacts.get('downloaded', '')}"
    if operation == "screenshot":
        return f"screenshot {artifacts.get('bytes', 0)} bytes → {artifacts.get('screenshot', '')}"
    if operation == "upload":
        return f"uploaded {artifacts.get('bytes', 0)} bytes from {artifacts.get('uploaded', '')}"
    if operation == "snapshot":
        return f"snapshot: {artifacts.get('title', '')} — {artifacts.get('url', '')}"
    return f"{operation} ok"

