"""Native tool: ``git`` (Final Build Plan §8.3).

Six operations over the ``git`` CLI as **list-argv subprocess**
(never a shell string): ``status`` · ``log`` · ``diff`` ·
``branch_list`` · ``add`` · ``commit``. The ``repo`` argument (the
working tree root) is scope-checked by the §8.2 Scope stage; ``add``
and ``commit`` are the declared mutations (a WRITE on the repo path).

Risk 2 — mirrors the platform's remote surface (read-only ``git``
operations at dl 1–2; the local WRITE composition is the §3.5
policy's job, and the scope stage routes it). Output is the honest
CLI text; ``exit_code`` rides the artifacts so the Verify stage
proves the effect.

الجِت — ست عمليات بقوائم معاملات، والمستودع خاضع للنطاق،
والكتابة مُعلنة.

Stdlib only.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
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
    DEFAULT_TIMEOUT_SECONDS,
    NativeTool,
    ToolArgError,
    object_schema,
    output_schema,
    require_int,
    require_operation,
    require_str,
)

_OPERATIONS: tuple[str, ...] = (
    "status",
    "log",
    "diff",
    "branch_list",
    "add",
    "commit",
)
_READ_OPERATIONS: tuple[str, ...] = ("status", "log", "diff", "branch_list")


class GitTool(NativeTool):
    """§8.3 ``git`` — CLI subprocess, scope-checked repo, risk 2."""

    name = "git"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:git",
            name=self.name,
            description=(
                "Git capability: status, log, diff, branch_list (reads) and "
                "add, commit (mutations) over a scope-checked repo path."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "repo": {
                        "type": "string",
                        "description": "repository working tree",
                    },
                    "message": {"type": "string", "description": "commit message"},
                    "limit": {"type": "integer", "description": "log entries"},
                },
                required=("op", "repo"),
            ),
            output_schema=output_schema("git CLI text + exit_code artifact"),
            permissions=("git.read", "git.write"),
            scope_requirements=ScopeRequirements(
                path_arguments=("repo",),
                mutating_operations=("add", "commit"),
                dimensions=("git", "filesystem"),
            ),
            risk=2,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        if operation in _READ_OPERATIONS:
            return VerificationSpec(V.EXIT_ZERO)
        return VerificationSpec(V.EXIT_ZERO)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        repo = Path(require_str(arguments, "repo"))
        if not repo.exists():
            raise ToolArgError("repo", f"no such repository path: {repo}")
        argv: list[str] = ["git"]
        if operation == "status":
            argv += ["status", "--porcelain"]
        elif operation == "log":
            limit = require_int(arguments, "limit", default=10, low=1, high=500)
            argv += ["log", f"-{limit}", "--oneline"]
        elif operation == "diff":
            argv += ["diff", "--stat"]
        elif operation == "branch_list":
            argv += ["branch", "--format=%(refname:short)"]
        elif operation == "add":
            argv += ["add", "--all"]
        else:  # commit
            message = require_str(arguments, "message")
            argv += ["commit", "-m", message]
        timeout = min(DEFAULT_TIMEOUT_SECONDS, 30)
        try:
            completed = subprocess.run(  # noqa: S603 — fixed argv prefix
                argv,
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolCallResult(
                output=f"git {operation} timed out after {timeout}s",
                artifacts={"exit_code": 124, "argv": argv},
            )
        output = completed.stdout.strip()
        if completed.stderr.strip():
            output = f"{output}\n[stderr] {completed.stderr.strip()}".strip()
        return ToolCallResult(
            output=output if output else f"[exit {completed.returncode}]",
            artifacts={
                "exit_code": completed.returncode,
                "argv": argv,
                "repo": str(repo),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )

    def capabilities(self) -> CapabilityReport:
        binary = shutil.which("git")
        if binary:
            return CapabilityReport(available=True, reason=f"git CLI at {binary}")
        return CapabilityReport(
            available=False, reason="git CLI not found on PATH"
        )
