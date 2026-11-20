"""Hardware Scanner (Final Build Plan §4.1 / Spec §89).

Discovers the twelve §4.1 targets and assembles a
:class:`HardwareProfile`. Three implementations:

* :class:`WindowsScanner` — Windows APIs/system libraries only
  (Plan §4.6): ``ctypes`` (GlobalMemoryStatusEx, drive
  enumeration, screen metrics), ``winreg`` (CPU name, GPU VRAM,
  edition, installed software), PowerShell CIM (processor/GPU/
  network/PnP where registry alone is not enough) and ``tasklist``
  for processes. Every probe is best-effort: a failing category
  degrades to empty, never to an exception — "where detectable".
* :class:`PosixScanner` — procfs/sysfs for dev & CI machines.
* :class:`StaticScanner` — returns a fixed profile (harness).

``default_scanner()`` picks by ``sys.platform``: the Windows box
scans Windows; everywhere else the POSIX scanner reports honestly.

This phase needs no agent framework (Plan §4.6, verbatim).
Optional enrichment: **psutil** (BSD-3-Clause, MODE A — pinned
7.2.2, docs/REPOSITORY-INTEGRATION.md) fills scanner gaps the
stdlib cannot (CPU max frequency on POSIX); Windows probing stays
on the system-library paths above.

ماسح العتاد — Windows APIs أولًا، وكل فئة best-effort بلا استثناءات؛
psutil (MODE A) يسد فجوات stdlib حيث يتوفر فقط.
"""

from __future__ import annotations

import csv
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from abc import ABC, abstractmethod
from types import ModuleType
from typing import Any

from .profile import (
    CpuInfo,
    DeviceEntry,
    DisplayInfo,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
    NetworkInfo,
    ProcessEntry,
    SoftwareEntry,
    StorageVolume,
    WindowsInfo,
)

_MB = 1024 * 1024
_CIM_TIMEOUT = 45
_TASKLIST_TIMEOUT = 60

# GPU adapter registry path (display adapters class GUID).
_GPU_CLASS_KEY = (
    r"SYSTEM\CurrentControlSet\Control\Class"
    r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
)
_UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
_NT_CURRENT_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
_CPU_KEY = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"


class HardwareScanner(ABC):
    """A source of hardware truth. ``scan`` never raises."""

    kind: str

    @abstractmethod
    def scan(self) -> HardwareProfile:
        """Assemble a full best-effort profile of this machine."""


def default_scanner() -> HardwareScanner:
    """Platform-appropriate scanner (win32 → WindowsScanner)."""
    if sys.platform == "win32":
        return WindowsScanner()
    return PosixScanner()


# -------------------------------------------------------------- winreg help


def _winreg() -> ModuleType | None:
    """The winreg module on Windows (None elsewhere)."""
    if sys.platform != "win32":
        return None
    import winreg

    return winreg


def _reg_str(hive_name: str, path: str, name: str) -> str | None:
    """One registry string value, best-effort (hive: HKLM | HKCU)."""
    winreg = _winreg()
    if winreg is None:
        return None
    hive = (
        winreg.HKEY_LOCAL_MACHINE
        if hive_name == "HKLM"
        else winreg.HKEY_CURRENT_USER
    )
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, name)
        return str(value)
    except OSError:
        return None


# ----------------------------------------------------------- Windows probes


def _powershell_cim(
    class_name: str, properties: list[str], *, first: int | None = None
) -> list[dict[str, Any]]:
    """Query one CIM class via PowerShell JSON output (best-effort)."""
    select = ",".join(properties)
    limit = f" | Select-Object -First {first}" if first else ""
    command = (
        "Get-CimInstance -ClassName "
        f"{class_name} | Select-Object {select}{limit} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            capture_output=True,
            timeout=_CIM_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    # PowerShell's text encoding follows the console code page — on
    # non-English Windows (Arabic CP-1256, for one) the bytes are NOT
    # valid UTF-8, and a strict text=True decode crashes the reader
    # thread and leaves stdout=None (a real-device bug this fix
    # closes). Bytes + replace-decoding keeps the JSON parse alive
    # and drops only the undecodable noise.
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    if result.returncode != 0 or not stdout.strip():
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    return []


def _registry_gpu_vram_mb(adapter_index: int) -> int | None:
    """64-bit GPU VRAM from the display-adapter registry; the CIM
    ``AdapterRAM`` uint32 wraps above 4 GB, so this is the truth
    when present."""
    winreg = _winreg()
    if winreg is None:
        return None
    try:
        key_path = _GPU_CLASS_KEY + f"\\{adapter_index:04d}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            data, _kind = winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")
        if isinstance(data, int):
            return data // _MB
        if isinstance(data, bytes) and len(data) >= 8:
            return int.from_bytes(data[:8], "little") // _MB
    except OSError:
        return None
    return None


def _memory_status_ex() -> tuple[int, int] | None:
    """(total_mb, available_mb) via GlobalMemoryStatusEx."""
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
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.ullTotalPhys // _MB, status.ullAvailPhys // _MB
    except Exception:  # noqa: BLE001 — best-effort by contract
        return None


_DRIVE_KINDS = {2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ramdisk"}


def _windows_drives() -> list[StorageVolume]:
    """Volumes via GetLogicalDrives + GetDriveTypeW + disk_usage."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        bitmask = kernel32.GetLogicalDrives()
        if bitmask == 0:
            return []
        volumes: list[StorageVolume] = []
        for letter in range(26):
            if not (bitmask >> letter) & 1:
                continue
            root = f"{chr(ord('A') + letter)}:\\"
            drive_type = kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
            if drive_type in (0, 1):
                continue
            total_mb = free_mb = None
            try:
                usage = shutil.disk_usage(root)
                total_mb, free_mb = usage.total // _MB, usage.free // _MB
            except OSError:
                pass
            volumes.append(
                StorageVolume(
                    mount=root,
                    kind=_DRIVE_KINDS.get(drive_type),
                    total_mb=total_mb,
                    free_mb=free_mb,
                )
            )
        return volumes
    except Exception:  # noqa: BLE001 — best-effort by contract
        return []


def _installed_software() -> list[SoftwareEntry]:
    """Uninstall-registry enumeration (HKLM 64/32 views + HKCU)."""
    winreg = _winreg()
    if winreg is None:
        return []
    try:
        views = (
            (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL_KEY, winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL_KEY, winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_CURRENT_USER, _UNINSTALL_KEY, 0),
        )
        entries: list[SoftwareEntry] = []
        for root, path, wow in views:
            try:
                base = winreg.OpenKey(root, path, 0, winreg.KEY_READ | wow)
            except OSError:
                continue
            with base:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(base, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(base, subkey_name) as subkey:
                            name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                            version: str | None = None
                            try:
                                raw, _ = winreg.QueryValueEx(subkey, "DisplayVersion")
                                version = str(raw)
                            except OSError:
                                pass
                    except OSError:
                        continue
                    clean = str(name).strip()
                    if clean:
                        entries.append(
                            SoftwareEntry(name=clean, version=version)
                        )
        unique = {entry.name: entry for entry in entries}
        return sorted(unique.values(), key=lambda entry: entry.name.lower())
    except Exception:  # noqa: BLE001 — best-effort by contract
        return []


def _tasklist_processes(limit: int = 400) -> list[ProcessEntry]:
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            timeout=_TASKLIST_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    # Same console-codepage discipline as _powershell_cim: tasklist on
    # non-English Windows emits non-UTF-8 bytes (Arabic process names).
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    entries: list[ProcessEntry] = []
    for row in csv.reader(io.StringIO(stdout)):
        if len(row) < 2:
            continue
        name = row[0].strip('" ')
        pid_text = row[1].strip('" ')
        if not name or not pid_text.isdigit():
            continue
        entries.append(ProcessEntry(pid=int(pid_text), name=name))
        if len(entries) >= limit:
            break
    return entries


def _windows_info() -> WindowsInfo | None:
    version = platform.release() or None
    if not version:
        return None
    build: str | None = None
    if sys.platform == "win32":
        try:
            build = str(sys.getwindowsversion().build)  # Windows only
        except (AttributeError, ValueError):
            pass
    edition = _reg_str("HKLM", _NT_CURRENT_VERSION, "ProductName")
    release = _reg_str("HKLM", _NT_CURRENT_VERSION, "DisplayVersion")
    if not release:
        release = _reg_str("HKLM", _NT_CURRENT_VERSION, "ReleaseId")
    return WindowsInfo(
        version=version,
        build=build,
        edition=edition,
        release=release,
        arch=platform.machine(),
    )


# ------------------------------------------------------------ the scanners


class WindowsScanner(HardwareScanner):
    """Windows 10+ hardware discovery via system libraries only
    (Plan §4.6 — no repositories, no agent framework)."""

    kind = "windows"

    def scan(self) -> HardwareProfile:
        gpus, displays = self._gpus_and_displays()
        return HardwareProfile(
            scanner_kind=self.kind,
            cpu=self._cpu(),
            gpus=gpus,
            ram=self._ram(),
            storage=_windows_drives(),
            displays=displays,
            windows=_windows_info(),
            network=self._network(),
            devices=self._devices(),
            installed_software=_installed_software(),
            processes=_tasklist_processes(),
        )

    # ------------------------------------------------------- CPU (§4.1)

    def _cpu(self) -> CpuInfo:
        name = _reg_str("HKLM", _CPU_KEY, "ProcessorNameString")
        clock_text = _reg_str("HKLM", _CPU_KEY, "~MHz")
        clock = int(float(clock_text)) if clock_text else None
        logical = os.cpu_count()
        physical: int | None = None
        rows = _powershell_cim(
            "Win32_Processor",
            ["Name", "NumberOfCores", "NumberOfLogicalProcessors", "MaxClockSpeed"],
        )
        if rows:
            row = rows[0]
            cim_name = str(row.get("Name") or "").strip()
            if cim_name:
                name = cim_name
            for key, target in (
                ("NumberOfCores", "physical"),
                ("NumberOfLogicalProcessors", "logical"),
                ("MaxClockSpeed", "clock"),
            ):
                try:
                    value = int(row.get(key) or 0)
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    if target == "physical":
                        physical = value
                    elif target == "logical":
                        logical = value
                    else:
                        clock = value
        return CpuInfo(
            name=name,
            arch=platform.machine(),
            physical_cores=physical,
            logical_cores=logical,
            max_clock_mhz=clock,
        )

    # ------------------------------------------------- GPU/VRAM + displays

    def _gpus_and_displays(
        self,
    ) -> tuple[list[GpuInfo], list[DisplayInfo]]:
        """One CIM pass yields GPUs (VRAM, driver) and per-adapter
        current resolutions — the Displays/Resolution §4.1 targets."""
        rows = _powershell_cim(
            "Win32_VideoController",
            [
                "Name",
                "DriverVersion",
                "AdapterRAM",
                "CurrentHorizontalResolution",
                "CurrentVerticalResolution",
            ],
        )
        gpus: list[GpuInfo] = []
        displays: list[DisplayInfo] = []
        for index, row in enumerate(rows):
            name = str(row.get("Name") or "").strip()
            if not name:
                continue
            vram: int | None = None
            adapter_ram = row.get("AdapterRAM")
            if isinstance(adapter_ram, int):
                vram = adapter_ram // _MB  # uint32 — wraps above 4 GB
            registry_vram = _registry_gpu_vram_mb(index)
            if registry_vram is not None:
                vram = registry_vram  # 64-bit truth beats the wrap
            driver = row.get("DriverVersion")
            gpus.append(
                GpuInfo(
                    name=name,
                    vendor=name.split()[0] if " " in name else None,
                    vram_mb=vram,
                    driver_version=str(driver) if driver else None,
                )
            )
            width = row.get("CurrentHorizontalResolution")
            height = row.get("CurrentVerticalResolution")
            if isinstance(width, int) and isinstance(height, int) and width > 0:
                displays.append(
                    DisplayInfo(name=name, width=width, height=height)
                )
        if not displays:
            primary = self._primary_display()
            if primary is not None:
                displays.append(primary)
        return gpus, displays

    def _primary_display(self) -> DisplayInfo | None:
        if sys.platform != "win32":
            return None
        try:
            import ctypes

            user32 = ctypes.windll.user32
            width = user32.GetSystemMetrics(0)
            height = user32.GetSystemMetrics(1)
            if width > 0 and height > 0:
                return DisplayInfo(name=None, width=width, height=height)
        except Exception:  # noqa: BLE001 — best-effort by contract
            return None
        return None

    # ------------------------------------------------------- RAM (§4.1)

    def _ram(self) -> MemoryInfo | None:
        memory = _memory_status_ex()
        if memory is None:
            return None
        return MemoryInfo(total_mb=memory[0], available_mb=memory[1])

    # --------------------------------------------------- Network (§4.1)

    def _network(self) -> NetworkInfo:
        adapters: list[dict[str, str | None]] = []
        for row in _powershell_cim(
            "Win32_NetworkAdapter",
            ["Name", "MACAddress", "NetEnabled"],
            first=64,
        ):
            name = str(row.get("Name") or "").strip()
            if not name:
                continue
            enabled = row.get("NetEnabled")
            mac = row.get("MACAddress")
            adapters.append(
                {
                    "name": name,
                    "mac": str(mac) if mac else None,
                    "status": "up" if enabled else "down",
                }
            )
        return NetworkInfo(hostname=socket.gethostname(), adapters=adapters)

    # -------------------------------------------- Devices (§4.1, capped)

    def _devices(self, limit: int = 250) -> list[DeviceEntry]:
        rows = _powershell_cim("Win32_PnPEntity", ["Name"], first=limit)
        return [
            DeviceEntry(name=str(row.get("Name") or "").strip())
            for row in rows
            if str(row.get("Name") or "").strip()
        ]


# ------------------------------------------------------------------- POSIX


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _meminfo_mb(key: str) -> int | None:
    text = _read_text("/proc/meminfo")
    if text is None:
        return None
    for line in text.splitlines():
        parts = line.split(":", 1)
        if parts[0].strip() == key and len(parts) > 1:
            digits = parts[1].strip().split()[0]
            if digits.isdigit():
                return int(digits) * 1024 // _MB
    return None


def _psutil_max_clock_mhz() -> int | None:
    """CPU max frequency via psutil (MODE A, optional — POSIX gap the
    stdlib leaves at ``None``). Best-effort, never raises."""
    try:
        import psutil  # noqa: PLC0415 — lazy: optional dependency
    except ImportError:
        return None
    try:
        freq = psutil.cpu_freq()
        if freq is not None and freq.max:
            return int(freq.max)
    except Exception:  # noqa: BLE001 — best-effort by contract
        pass
    return None


class PosixScanner(HardwareScanner):
    """Honest procfs/sysfs discovery for dev & CI machines. GPU and
    resolution detection is platform-specific beyond stdlib — those
    categories stay empty *where not detectable* (Plan §4.3 wording)."""

    kind = "posix"

    def scan(self) -> HardwareProfile:
        return HardwareProfile(
            scanner_kind=self.kind,
            cpu=self._cpu(),
            gpus=[],
            ram=self._ram(),
            storage=self._storage(),
            displays=[],
            windows=None,
            network=self._network(),
            devices=[],
            installed_software=[],
            processes=self._processes(),
        )

    def _cpu(self) -> CpuInfo:
        name: str | None = None
        logical = os.cpu_count()
        physical: int | None = None
        text = _read_text("/proc/cpuinfo")
        if text:
            processors = 0
            sockets: set[str] = set()
            cores: set[tuple[str, str]] = set()
            current_socket = "0"
            for line in text.splitlines():
                key, _, value = line.partition(":")
                key = key.strip()
                if key == "model name" and not name:
                    name = value.strip()
                elif key == "processor":
                    processors += 1
                elif key == "physical id":
                    current_socket = value.strip()
                    sockets.add(current_socket)
                elif key == "core id":
                    cores.add((current_socket, value.strip()))
            if processors:
                logical = processors
            if cores:
                physical = len(cores)
        return CpuInfo(
            name=name,
            arch=platform.machine(),
            physical_cores=physical,
            logical_cores=logical,
            max_clock_mhz=_psutil_max_clock_mhz(),
        )

    def _ram(self) -> MemoryInfo | None:
        total = _meminfo_mb("MemTotal")
        if not total:
            return None
        return MemoryInfo(total_mb=total, available_mb=_meminfo_mb("MemAvailable"))

    def _storage(self, limit: int = 8) -> list[StorageVolume]:
        volumes: list[StorageVolume] = []
        seen: set[str] = set()
        mounts_text = _read_text("/proc/self/mounts")
        if mounts_text:
            for line in mounts_text.splitlines():
                parts = line.split()
                if len(parts) < 3 or not parts[0].startswith("/dev/"):
                    continue
                mountpoint = parts[1].replace("\\040", " ")
                if mountpoint in seen:
                    continue
                seen.add(mountpoint)
                try:
                    usage = shutil.disk_usage(mountpoint)
                except OSError:
                    continue
                volumes.append(
                    StorageVolume(
                        mount=mountpoint,
                        kind=parts[2],
                        total_mb=usage.total // _MB,
                        free_mb=usage.free // _MB,
                    )
                )
                if len(volumes) >= limit:
                    return volumes
        if not volumes:
            try:
                usage = shutil.disk_usage("/")
                volumes.append(
                    StorageVolume(
                        mount="/",
                        kind="root",
                        total_mb=usage.total // _MB,
                        free_mb=usage.free // _MB,
                    )
                )
            except OSError:
                pass
        return volumes

    def _network(self) -> NetworkInfo:
        adapters: list[dict[str, str | None]] = []
        try:
            import glob

            for path in sorted(glob.glob("/sys/class/net/*")):
                name = path.rsplit("/", 1)[-1]
                mac = _read_text(f"{path}/address")
                state = _read_text(f"{path}/operstate")
                adapters.append(
                    {
                        "name": name,
                        "mac": mac.strip() if mac and mac.strip() else None,
                        "status": state.strip() if state else None,
                    }
                )
        except Exception:  # noqa: BLE001 — best-effort by contract
            pass
        return NetworkInfo(hostname=socket.gethostname(), adapters=adapters)

    def _processes(self, limit: int = 400) -> list[ProcessEntry]:
        entries: list[ProcessEntry] = []
        try:
            pids = [entry for entry in os.listdir("/proc") if entry.isdigit()]
            for pid in sorted(pids, key=int):
                comm = _read_text(f"/proc/{pid}/comm")
                if comm is None:
                    continue
                entries.append(ProcessEntry(pid=int(pid), name=comm.strip() or "?"))
                if len(entries) >= limit:
                    break
        except OSError:
            pass
        return entries


# ------------------------------------------------------------------ static


class StaticScanner(HardwareScanner):
    """Returns a fixed profile — deterministic harness input."""

    kind = "static"

    def __init__(self, profile: HardwareProfile) -> None:
        self._profile = profile

    def scan(self) -> HardwareProfile:
        fresh = self._profile.copy()
        fresh.scanner_kind = self.kind
        return fresh
