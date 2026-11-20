"""Native tool: ``process`` (Final Build Plan §8.3).

Three operations — ``list`` · ``info`` · ``kill``:

* **list** — rich rows via psutil (the MODE A ``[hardware]`` extra)
  when installed; an honest minimal view from ``/proc`` on Linux;
  otherwise unavailable (reported, never faked);
* **info** — one process record by pid (same ladders);
* **kill** — ``os.kill`` (POSIX SIGTERM default / Windows
  TerminateProcess) with an honest exit code.

The tool mirrors the platform's own remote surface (``ps_get_process``
dl 1, ``win_process_kill_tree`` dl 2+confirm): NEXUS rates it risk 2
— the kill operation is the mutation.

عمليات النظام — قائمة ومعلومات وإنهاء، بسلّم انحدار صادق.

Stdlib only (psutil optional, MODE A).
"""

from __future__ import annotations

import os
import signal
import sys
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
    NativeTool,
    ToolArgError,
    object_schema,
    output_schema,
    require_int,
    require_operation,
)

_OPERATIONS: tuple[str, ...] = ("list", "info", "kill")


def _psutil():
    try:
        import psutil  # MODE A optional companion

        return psutil
    except ImportError:
        return None


def _proc_rows(limit: int) -> list[dict[str, Any]] | None:
    """Minimal /proc view (Linux) — None when impossible on this OS."""
    if sys.platform.startswith("linux"):
        rows: list[dict[str, Any]] = []
        for entry in sorted(os.listdir("/proc"))[:400]:
            if not entry.isdigit():
                continue
            try:
                comm = (Path("/proc") / entry / "comm").read_text().strip()
            except OSError:
                continue
            rows.append({"pid": int(entry), "name": comm})
            if len(rows) >= limit:
                break
        return rows
    return None


class ProcessTool(NativeTool):
    """§8.3 ``process`` — list/info/kill, risk 2."""

    name = "process"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:process",
            name=self.name,
            description=(
                "Process capability: list (psutil or /proc ladder), info(pid), "
                "kill(pid, signal). Kill is the mutating operation."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "pid": {"type": "integer", "description": "target pid"},
                    "limit": {"type": "integer", "description": "list bound"},
                },
                required=("op",),
            ),
            output_schema=output_schema("process rows / record / kill result"),
            permissions=("process.read", "process.control"),
            scope_requirements=ScopeRequirements(
                path_arguments=(),
                mutating_operations=("kill",),
                dimensions=("process",),
            ),
            risk=2,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        if operation == "list":
            return VerificationSpec(V.OUTPUT_NONEMPTY)
        if operation == "info":
            return VerificationSpec(V.JSON_FIELD, "process")
        if operation == "kill":
            return VerificationSpec(V.EXIT_ZERO)
        return VerificationSpec(V.NONE)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        if operation == "list":
            limit = require_int(
                arguments, "limit", default=50, low=1, high=1000
            )
            psutil = _psutil()
            if psutil is not None:
                rows = [
                    {
                        "pid": proc.pid,
                        "name": proc.info["name"] or "?",
                        "rss_mb": round(
                            ((proc.info["memory_info"].rss)
                            if proc.info["memory_info"] is not None else 0)
                            / (1024 * 1024),
                            1,
                        ),
                    }
                    for proc in psutil.process_iter(["pid", "name", "memory_info"])
                ][:limit]
                source = "psutil"
            else:
                raw = _proc_rows(limit)
                if raw is None:
                    raise ToolArgError(
                        "op",
                        "process listing needs psutil ([hardware] extra) "
                        "or /proc (Linux) on this platform",
                    )
                rows = raw
                source = "/proc"
            lines = [f"{row['pid']:>7}  {row['name']}" for row in rows]
            return ToolCallResult(
                output="\n".join(lines),
                artifacts={"processes": rows, "source": source},
            )

        pid = require_int(arguments, "pid", default=0, low=1, high=1 << 22)
        if operation == "info":
            record = self._info(pid)
            return ToolCallResult(
                output=str(record), artifacts={"process": record, "pid": pid}
            )

        # kill
        if pid == os.getpid():
            raise ToolArgError("pid", "refusing to kill the NEXUS process itself")
        try:
            if sys.platform == "win32":
                os.kill(pid, 9)  # TerminateProcess
            else:
                os.kill(pid, signal.SIGTERM)
            return ToolCallResult(
                output=f"signaled pid {pid}",
                artifacts={"exit_code": 0, "pid": pid},
            )
        except ProcessLookupError:
            return ToolCallResult(
                output=f"no such process: {pid}",
                artifacts={"exit_code": 1, "pid": pid, "not_found": True},
            )
        except PermissionError as exc:
            return ToolCallResult(
                output=f"permission denied killing {pid}: {exc}",
                artifacts={"exit_code": 1, "pid": pid},
            )

    def _info(self, pid: int) -> dict[str, Any]:
        psutil = _psutil()
        if psutil is not None:
            proc = psutil.Process(pid)
            return {
                "pid": pid,
                "name": proc.name(),
                "status": proc.status(),
                "rss_mb": round(proc.memory_info().rss / (1024 * 1024), 1),
            }
        if sys.platform.startswith("linux"):
            base = Path("/proc") / str(pid)
            try:
                comm = (base / "comm").read_text().strip()
                status = "running"
                for line in (base / "status").read_text().splitlines():
                    if line.startswith("State:"):
                        status = line.split(":", 1)[1].strip()
                return {"pid": pid, "name": comm, "status": status}
            except OSError as exc:
                raise ToolArgError("pid", f"cannot read /proc/{pid}: {exc}") from exc
        raise ToolArgError(
            "pid", "process info needs psutil or /proc on this platform"
        )

    def capabilities(self) -> CapabilityReport:
        psutil = _psutil()
        if psutil is not None:
            return CapabilityReport(
                available=True, reason="psutil installed (MODE A [hardware])"
            )
        if sys.platform.startswith("linux"):
            return CapabilityReport(
                available=True, reason="/proc ladder (psutil not installed)"
            )
        return CapabilityReport(
            available=False,
            reason="needs psutil (pip install nexus-core[hardware]) on this platform",
        )
