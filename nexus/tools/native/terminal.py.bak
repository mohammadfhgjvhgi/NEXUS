"""Native tool: ``terminal`` (Final Build Plan §8.3).

One operation — ``run`` — a single command as a **list** (never a
shell string): ``subprocess.run([command, *args])`` with a hard
timeout (1..300 s, default 30), captured stdout/stderr, an honest
exit code, and the ``cwd`` scope-checked by the router. Risk is 3
(host-level execution — the same level the platform's remote surface
assigns ``code_run_cmd``); with the default
``tools.confirm_danger_above = 2`` every terminal call passes a human
confirmation gate before executing.

الطرفية — أمر واحد كقائمة لا كنص، ومهلة صارمة، ورمز خروج
صادق، وخطر 3 يتطلب تأكيدًا بشريًا.

Stdlib only.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from typing import Any

from ..models import (
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
    optional_str,
    output_schema,
    require_int,
    require_operation,
    require_str,
)

_OPERATIONS: tuple[str, ...] = ("run",)


class TerminalTool(NativeTool):
    """§8.3 ``terminal`` — list-argv command execution, risk 3."""

    name = "terminal"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:terminal",
            name=self.name,
            description=(
                "Run one command as an argument list (no shell): "
                "{command, args[], timeout_seconds, cwd}. Captured output, "
                "honest exit code, hard timeout."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "command": {"type": "string", "description": "binary to run"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "arguments (never shell-parsed)",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "1..300, default 30",
                    },
                    "cwd": {"type": "string", "description": "working directory"},
                },
                required=("op", "command"),
            ),
            output_schema=output_schema(
                "captured stdout/stderr + exit_code artifact"
            ),
            permissions=("terminal.execute",),
            scope_requirements=ScopeRequirements(
                path_arguments=("cwd",),
                mutating_operations=(),  # every execution acts
                dimensions=("process", "filesystem"),
            ),
            risk=3,
            verification=VerificationSpec(V.EXIT_ZERO),
            version="1.0.0",
        )

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        require_operation(arguments, _OPERATIONS)
        command = require_str(arguments, "command")
        raw_args = arguments.get("args", [])
        if not isinstance(raw_args, list) or any(
            not isinstance(item, str) for item in raw_args
        ):
            raise ToolArgError("args", "must be a list of strings")
        timeout = require_int(
            arguments,
            "timeout_seconds",
            default=DEFAULT_TIMEOUT_SECONDS,
            low=1,
            high=300,
        )
        cwd = optional_str(arguments, "cwd")
        argv = [command, *raw_args]
        try:
            completed = subprocess.run(  # noqa: S603 — argv is a checked list
                argv,
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolCallResult(
                output=f"timeout after {timeout}s: {' '.join(argv[:4])}…",
                artifacts={"exit_code": 124, "argv": argv, "timed_out": True},
            )
        except FileNotFoundError:
            return ToolCallResult(
                output=f"command not found: {command!r}",
                artifacts={"exit_code": 127, "argv": argv},
            )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        parts = [stdout.strip()]
        if stderr.strip():
            parts.append(f"[stderr] {stderr.strip()}")
        parts.append(f"[exit {completed.returncode}]")
        return ToolCallResult(
            output="\n".join(part for part in parts if part),
            artifacts={
                "exit_code": completed.returncode,
                "argv": argv,
                "stdout": stdout,
                "stderr": stderr,
            },
        )

    def capabilities(self) -> Any:
        from ..models import CapabilityReport

        return CapabilityReport(
            available=True,
            reason="subprocess.run with list argv is cross-platform",
        )
