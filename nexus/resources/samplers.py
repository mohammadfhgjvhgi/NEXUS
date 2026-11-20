"""Utilization samplers — live CPU/RAM/VRAM readings (Spec §90).

Best-effort by contract: every value may be ``None`` when the
platform cannot report it (headless CI, VRAM without vendor APIs).
Samplers that need a baseline keep internal state and return
``None`` on their first call.

Optional enrichment: **psutil** (BSD-3-Clause, MODE A — pinned
7.2.2, see docs/REPOSITORY-INTEGRATION.md) fills the cross-platform
gaps the stdlib cannot: RSS on Windows, external-process memory.
It is imported lazily and every use degrades silently when absent —
the stdlib paths remain the always-available floor.

قياس الاستخدام الحي — CPU/RAM عبر نظام التشغيل، وVRAM حيث يمكن رصده؛
psutil (MODE A) يكمل الفجوات عبر المنصات عند توفره فقط.
"""

from __future__ import annotations

import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

_MB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Utilization:
    """One utilization reading (None = not measurable)."""

    cpu_percent: float | None = None
    ram_used_mb: int | None = None
    ram_total_mb: int | None = None
    vram_used_mb: int | None = None
    sampled_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "ram_used_mb": self.ram_used_mb,
            "ram_total_mb": self.ram_total_mb,
            "vram_used_mb": self.vram_used_mb,
            "sampled_at": self.sampled_at.isoformat(),
        }


class UtilizationSampler(ABC):
    """Source of live utilization readings (best-effort)."""

    @abstractmethod
    def sample(self) -> Utilization:
        """Take one reading; never raises."""


class PosixUtilizationSampler(UtilizationSampler):
    """/proc/stat deltas for CPU, /proc/meminfo for RAM."""

    def __init__(self) -> None:
        self._last_cpu: tuple[int, int, int] | None = None  # idle, busy, total

    def sample(self) -> Utilization:
        cpu_percent = self._cpu_percent()
        ram_used = ram_total = None
        total = _meminfo_mb("MemTotal")
        available = _meminfo_mb("MemAvailable")
        if total and available is not None:
            ram_total, ram_used = total, max(total - available, 0)
        return Utilization(
            cpu_percent=cpu_percent, ram_used_mb=ram_used, ram_total_mb=ram_total
        )

    def _cpu_percent(self) -> float | None:
        try:
            with open("/proc/stat", encoding="ascii") as handle:
                first = handle.readline()
        except OSError:
            return None
        values = first.split()[1:]
        if len(values) < 5 or not all(v.isdigit() for v in values[:5]):
            return None
        user, nice, system, idle, iowait = (int(v) for v in values[:5])
        idle_all = idle + iowait
        total = user + nice + system + idle_all
        busy = total - idle_all
        previous = self._last_cpu
        self._last_cpu = (idle_all, busy, total)
        if previous is None:
            return None
        d_idle = idle_all - previous[0]
        d_total = total - previous[2]
        if d_total <= 0:
            return None
        return round((1.0 - d_idle / d_total) * 100.0, 1)

    def _reset(self) -> None:
        self._last_cpu = None


def _meminfo_mb(key: str) -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                parts = line.split(":", 1)
                if parts[0].strip() == key and len(parts) > 1:
                    digits = parts[1].strip().split()[0]
                    if digits.isdigit():
                        return int(digits) * 1024 // _MB
    except OSError:
        pass
    return None


class WindowsUtilizationSampler(UtilizationSampler):
    """GlobalMemoryStatusEx for RAM + memory load, GetSystemTimes
    deltas for CPU (baseline kept internally)."""

    def __init__(self) -> None:
        self._last_times: tuple[int, int] | None = None  # (idle, total)

    def sample(self) -> Utilization:
        memory = self._memory_status()
        cpu_percent = self._cpu_percent()
        ram_total = memory[0] if memory else None
        ram_used = memory[2] if memory else None
        return Utilization(
            cpu_percent=cpu_percent, ram_used_mb=ram_used, ram_total_mb=ram_total
        )

    def _memory_status(self) -> tuple[int, int, int] | None:
        """(total_mb, available_mb, used_mb)."""
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(
                ctypes.byref(status)
            ):
                return None
            total = status.ullTotalPhys // _MB
            available = status.ullAvailPhys // _MB
            return total, available, max(total - available, 0)
        except Exception:  # noqa: BLE001 — best-effort by contract
            return None

    def _cpu_percent(self) -> float | None:
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            idle = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            ):
                return None

            def _quad(filetime: Any) -> int:
                return filetime.dwHighDateTime << 32 | filetime.dwLowDateTime

            idle_total = _quad(idle)
            # GetSystemTimes: kernel time INCLUDES idle time.
            system_total = _quad(kernel) + _quad(user)
            previous = self._last_times
            self._last_times = (idle_total, system_total)
            if previous is None:
                return None
            d_idle = idle_total - previous[0]
            d_total = system_total - previous[1]
            if d_total <= 0:
                return None
            return round((1.0 - d_idle / d_total) * 100.0, 1)
        except Exception:  # noqa: BLE001 — best-effort by contract
            return None


class StaticUtilizationSampler(UtilizationSampler):
    """Fixed readings — deterministic harness input."""

    def __init__(
        self,
        *,
        cpu_percent: float | None = None,
        ram_used_mb: int | None = None,
        ram_total_mb: int | None = None,
        vram_used_mb: int | None = None,
    ) -> None:
        self._utilization = Utilization(
            cpu_percent=cpu_percent,
            ram_used_mb=ram_used_mb,
            ram_total_mb=ram_total_mb,
            vram_used_mb=vram_used_mb,
        )

    def sample(self) -> Utilization:
        return self._utilization


def default_sampler() -> UtilizationSampler:
    """Platform-appropriate sampler (win32 → Windows)."""
    if sys.platform == "win32":
        return WindowsUtilizationSampler()
    return PosixUtilizationSampler()


def monotonic_ms() -> float:
    """Clock helper (avoids the deprecated time.clock)."""
    return time.monotonic() * 1000.0


def _optional_psutil() -> ModuleType | None:
    """psutil when installed (optional MODE A dependency — pin 7.2.2).

    Never a hard requirement: the stdlib floor below stays the source
    of truth whenever psutil is absent (fresh CI, minimal installs).
    """
    try:
        import psutil  # noqa: PLC0415 — lazy by design (optional dep)
    except ImportError:
        return None
    return psutil


def process_rss_mb() -> int | None:
    """This process's resident memory (resource-self-awareness).

    psutil first (cross-platform, including Windows where
    ``/proc/self/statm`` does not exist), then the procfs floor.
    """
    psutil = _optional_psutil()
    if psutil is not None:
        try:
            return int(psutil.Process().memory_info().rss // _MB)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — best-effort by contract
            pass
    try:
        with open("/proc/self/statm", encoding="ascii") as handle:
            pages = int(handle.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") // _MB
    except (OSError, ValueError, IndexError):
        return None
