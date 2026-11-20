"""Native tool: ``github`` (Final Build Plan §8.3).

Five operations over the GitHub REST API via :mod:`urllib` (no
client dependency): ``me`` · ``repo_info`` · ``list_branches`` ·
``list_issues`` · ``create_issue``.

Design notes:

* **offline-provable** — :meth:`GithubTool.build_request` is pure
  construction (URL/headers/body) and is unit-tested without any
  network; live calls only happen in ``handler``;
* **honest network** — every failure (offline, 4xx/5xx, timeout) is
  an actionable error, never a crash; the §8.2 Scope stage gates the
  host through the task's network policy;
* **token hygiene** — the token comes from ``NEXUS_GITHUB_TOKEN``
  (or the ``token`` argument), rides an Authorization header, and is
  never echoed into outputs or artifacts.

GitHub is an external service: dimensions ``network`` + ``external``
— the network policy applies. Risk 2 (reads + one mutating op).

أداة GitHub — بناء الطلب قابل للإثبات دون شبكة، والرمز
لا يُطبع أبدًا، والفشل صريح.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from ..models import (
    CapabilityReport,
    ScopeRequirements,
    ToolCallResult,
    ToolDefinition,
    VerificationSpec,
)
from ..models import (
    VerificationStrategy as V,
)
from .base import (
    NativeTool,
    ToolArgError,
    object_schema,
    output_schema,
    require_operation,
    require_str,
)

_OPERATIONS: tuple[str, ...] = (
    "me",
    "repo_info",
    "list_branches",
    "list_issues",
    "create_issue",
)
_API_ROOT = "https://api.github.com"
_TIMEOUT_SECONDS = 15


class GithubTool(NativeTool):
    """§8.3 ``github`` — REST client, offline-provable construction."""

    name = "github"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:github",
            name=self.name,
            description=(
                "GitHub REST capability: me, repo_info(owner/repo), "
                "list_branches, list_issues, create_issue. "
                "Token from NEXUS_GITHUB_TOKEN; never echoed."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "repo": {"type": "string", "description": "owner/repo"},
                    "title": {"type": "string", "description": "issue title"},
                    "body": {"type": "string", "description": "issue body"},
                    "token": {"type": "string", "description": "PAT override"},
                    "limit": {"type": "integer"},
                },
                required=("op",),
            ),
            output_schema=output_schema("GitHub REST payload + status"),
            permissions=("network.http", "github.api"),
            scope_requirements=ScopeRequirements(
                path_arguments=(),
                mutating_operations=("create_issue",),
                dimensions=("network", "external"),
            ),
            risk=2,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        if operation == "repo_info":
            return VerificationSpec(V.JSON_FIELD, "repo")
        if operation == "me":
            return VerificationSpec(V.JSON_FIELD, "user")
        if operation == "create_issue":
            return VerificationSpec(V.JSON_FIELD, "issue")
        return VerificationSpec(V.NONE)

    # ------------------------------------------------------- request building

    @staticmethod
    def build_request(
        operation: str, arguments: Mapping[str, Any], *, token: str | None = None
    ) -> urllib.request.Request:
        """Pure request construction (offline-provable §8.1 input→URL)."""
        if operation not in _OPERATIONS:
            raise ToolArgError("op", f"must be one of {list(_OPERATIONS)}")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nexus-tool-github/1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if operation == "me":
            return urllib.request.Request(f"{_API_ROOT}/user", headers=headers)
        repo = require_str(arguments, "repo")
        if "/" not in repo:
            raise ToolArgError("repo", "must be owner/repo")
        owner, name = repo.split("/", 1)
        if operation == "repo_info":
            return urllib.request.Request(
                f"{_API_ROOT}/repos/{owner}/{name}", headers=headers
            )
        if operation == "list_branches":
            return urllib.request.Request(
                f"{_API_ROOT}/repos/{owner}/{name}/branches?per_page=30",
                headers=headers,
            )
        if operation == "list_issues":
            return urllib.request.Request(
                f"{_API_ROOT}/repos/{owner}/{name}/issues?state=open&per_page=30",
                headers=headers,
            )
        # create_issue
        title = require_str(arguments, "title")
        payload = json.dumps({"title": title, "body": arguments.get("body", "")})
        return urllib.request.Request(
            f"{_API_ROOT}/repos/{owner}/{name}/issues",
            data=payload.encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )

    # ---------------------------------------------------------------- handler

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        token = os.environ.get("NEXUS_GITHUB_TOKEN") or (
            arguments.get("token") if isinstance(arguments.get("token"), str) else None
        )
        request = self.build_request(operation, arguments, token=token)
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            return ToolCallResult(
                output=f"github {operation}: HTTP {exc.code} {exc.reason}",
                artifacts={"status": exc.code, "exit_code": 1},
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return ToolCallResult(
                output=f"github {operation}: network failure ({exc})",
                artifacts={"status": 0, "exit_code": 1},
            )
        payload: Any = json.loads(raw or b"null")
        artifacts: dict[str, Any] = {"status": status, "exit_code": 0}
        if operation == "me":
            artifacts["user"] = {"login": payload.get("login"), "id": payload.get("id")}
            output = str(artifacts["user"])
        elif operation == "repo_info":
            artifacts["repo"] = {
                "full_name": payload.get("full_name"),
                "default_branch": payload.get("default_branch"),
                "stars": payload.get("stargazers_count"),
            }
            output = str(artifacts["repo"])
        elif operation == "create_issue":
            artifacts["issue"] = {
                "number": payload.get("number"),
                "url": payload.get("html_url"),
            }
            output = str(artifacts["issue"])
        else:
            output = f"{len(payload) if isinstance(payload, list) else 1} record(s)"
        return ToolCallResult(output=output, artifacts=artifacts)

    def capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            available=True,
            reason="REST client ready — per-call network errors are honest",
            detail={"api_root": _API_ROOT},
        )
