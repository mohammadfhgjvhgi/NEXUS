"""The GitHub REST client (New Plan §16.2) — stdlib urllib, honest limits.

One narrow surface that the :class:`~nexus.github.engine.GitHubEngine`
speaks through:

* ``request(method, route, ...)`` — one JSON-API call; 2xx returns the
  decoded body, 404 raises :class:`NotFoundError`, 403/429 raise
  :class:`RateLimitExceededError` with the ``X-RateLimit-Reset`` epoch, and
  any other failure raises :class:`GitHubError` with the *route* —
  never a token.
* Token support is §124-shaped: pass a
  :class:`~nexus.github.contracts.TokenRef`; the client resolves it
  per-call, puts it in the ``Authorization`` header only, and every
  error path masks credentials.

The base URL is injectable so tests run a real local HTTP server —
the parsing/error/header law is proven against real HTTP, not mocks.

عميل REST بمعايير صادقة: 404 صادق، والحدّ بـreset حقيقي، والتوكن في
الترويسة فقط لا في أي رسالة.

Stdlib only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from .contracts import (
    GitHubError,
    NotFoundError,
    RateLimitExceededError,
    TokenRef,
)

DEFAULT_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "NEXUS-GitHub-Engine/0.16 (+local-first; stdlib-urllib)"
_DEFAULT_TIMEOUT = 30


class GitHubClient:
    """One client per base URL; stateless beyond the base and timeout."""

    def __init__(
        self,
        base: str = DEFAULT_BASE,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------ plumbing

    def _headers(
        self, token: str | None, *, accept: str = "application/vnd.github+json"
    ) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _mask(exc: BaseException) -> str:
        text = str(exc)
        # paranoia belt: a header echo can never survive to the caller
        if "Authorization" in text or "Bearer" in text:
            return "[masked]"
        return text

    def request(
        self,
        method: str,
        route: str,
        *,
        params: dict[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        token_ref: TokenRef | None = None,
        accept: str = "application/vnd.github+json",
        raw: bool = False,
    ) -> Any:
        """One REST call.  ``route`` starts with '/' (e.g. ``/search/repositories``)."""
        url = self.base + route
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            url = url + "?" + urllib.parse.urlencode(clean)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        token: str | None = None
        if token_ref is not None:
            token = token_ref.resolve()  # TokenNotAvailableError surfaces honestly
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(token, accept=accept),
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
                if raw:
                    return payload
                if not payload:
                    return {}
                try:
                    return json.loads(payload.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return {"_raw_bytes": len(payload)}
        except urllib.error.HTTPError as exc:
            reset = exc.headers.get("X-RateLimit-Reset")
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:  # noqa: BLE001 — the status line is enough
                pass
            masked = self._mask(exc)
            if exc.code == 404:
                raise NotFoundError(f"{method} {route} -> 404: {detail}") from exc
            if exc.code in (403, 429):
                raise RateLimitExceededError(
                    f"{method} {route} -> {exc.code} (rate limit; reset_epoch={reset}): {masked}",
                    reset_epoch=int(reset) if reset and reset.isdigit() else None,
                ) from exc
            raise GitHubError(f"{method} {route} -> {exc.code}: {masked}") from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"{method} {route} -> network error: {self._mask(exc)}") from exc
        except TimeoutError as exc:
            raise GitHubError(f"{method} {route} -> timeout after {self.timeout}s") from exc

    def paginate(
        self,
        route: str,
        *,
        params: dict[str, Any] | None = None,
        token_ref: TokenRef | None = None,
        max_pages: int = 1,
    ) -> list[Any]:
        """Follow GitHub's page links up to ``max_pages`` (1 by default)."""
        page_params = dict(params or {})
        items: list[Any] = []
        for page in range(1, max_pages + 1):
            page_params["page"] = page
            page_params["per_page"] = page_params.get("per_page", 30)
            batch = self.request("GET", route, params=page_params, token_ref=token_ref)
            if not isinstance(batch, list):
                return items + ([batch] if batch else [])
            items.extend(batch)
            if len(batch) < page_params["per_page"]:
                break
        return items
