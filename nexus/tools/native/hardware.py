"""Native tool: ``hardware`` (Final Build Plan §8.3).

Three operations — ``snapshot`` · ``cpu`` · ``disk`` — pure stdlib
system introspection (the Phase-3 ``HardwareScanner`` is the deep
scan; this is the always-available runtime view):

* CPU: count, load average (POSIX), frequency via psutil when present;
* memory: ``/proc/meminfo`` (Linux) or ``GlobalMemoryStatusEx``
  (Windows, ctypes) — total/available;
* disk: :func:`shutil.disk_usage` on the given path (default root).

Risk 0 — read-only observation (the platform's ``sys_os_info`` sits
at dl 0 for exactly this reason).

أداة العتاد — قراءة صافية للنظام: المعالج والذاكرة والقرص.

Stdlib only.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
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
    object_schema,
    optional_str,
    output_schema,
    require_operation,
)

_OPERATIONS: tuple[str, ...] = ("snapshot", "cpu", "disk")


def _memory_linux() -> tuple[int, int] | None:
    try:
        fields: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, raw = line.partition(":")
            fields[key.strip()] = int(raw.strip().split()[0]) * 1024
        total = fields.get("MemTotal", 0)
        available = fields.get("MemAvailable", total)
        return (total, available) if total else None
    except OSError:
        return None


def _memory_windows() -> tuple[int, int] | None:
    class _MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(  # type: ignore[attr-defined]
        ctypes.byref(status)
    ):
        return None
    return (status.ullTotalPhys, status.ullAvailPhys)


def memory_state() -> dict[str, Any]:
    """(total, available) bytes — honest degradation when unreadable."""
    probe = _memory_windows() if sys.platform == "win32" else _memory_linux()
    if probe is None:
        return {"total_mb": None, "available_mb": None, "source": "unavailable"}
    total, available = probe
    return {
        "total_mb": round(total / (1024 * 1024)),
        "available_mb": round(available / (1024 * 1024)),
        "source": "win32/GlobalMemoryStatusEx" if sys.platform == "win32" else "/proc/meminfo",
    }


class HardwareTool(NativeTool):
    """§8.3 ``hardware`` — stdlib system introspection, risk 0."""

    name = "hardware"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:hardware",
            name=self.name,
            description=(
                "Hardware/system observation: snapshot (cpu+memory+disk+"
                "platform), cpu, disk(path). Read-only, risk 0."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "path": {"type": "string", "description": "disk usage path"},
                },
                required=("op",),
            ),
            output_schema=output_schema("system observation record"),
            permissions=("hardware.read",),
            scope_requirements=ScopeRequirements(
                path_arguments=("path",),
                mutating_operations=(),
                dimensions=("hardware",),
            ),
            risk=0,
            verification=VerificationSpec(V.OUTPUT_NONEMPTY),
            version="1.0.0",
        )

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        if operation == "cpu":
            record = self._cpu()
            return ToolCallResult(output=str(record), artifacts={"cpu": record})
        if operation == "disk":
            path = optional_str(arguments, "path") or (
                "C:\\" if sys.platform == "win32" else "/"
            )
            usage = shutil.disk_usage(path)
            record = {
                "path": path,
                "total_gb": round(usage.total / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
            }
            return ToolCallResult(output=str(record), artifacts={"disk": record})
        record = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu": self._cpu(),
            "memory": memory_state(),
        }
        return ToolCallResult(output=str(record), artifacts={"snapshot": record})

    def _cpu(self) -> dict[str, Any]:
        record: dict[str, Any] = {"count": os.cpu_count() or 1}
        if hasattr(os, "getloadavg"):
            try:
                record["loadavg"] = [round(v, 2) for v in os.getloadavg()]
            except OSError:
                record["loadavg"] = "unavailable"
        try:
            import psutil  # MODE A optional companion

            freq = psutil.cpu_freq()
            if freq is not None:
                record["mhz"] = round(freq.current)
        except ImportError:
            pass
        return record

    def capabilities(self) -> CapabilityReport:
        return CapabilityReport(
            available=True,
            reason="stdlib system introspection (cpu/disk always; memory per-OS)",
            detail={"platform": sys.platform},
        )
