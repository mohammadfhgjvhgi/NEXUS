"""Hardware Profile model (Final Build Plan §4.1–§4.2 / Spec §89).

The scanner's twelve detection targets (Plan §4.1, verbatim):

    CPU · GPU · VRAM · RAM · Storage · Displays · Resolution ·
    Windows · Network · Devices · Installed software · Processes

map onto typed profile fields (VRAM is a GPU attribute, resolution a
display attribute — both stay first-class via the GPU/display
entries).

§4.2 (verbatim): the profile is persisted as ``hardware_profile``
and **never relies on model memory** — this is *system data*. It
lives as one atomic JSON record under ``NexusPaths.data``
(``hardware_profile.json``), written with the §2.5 crash discipline
(temp file + ``os.replace`` + ``fsync``) and keyed by the
``nexus.hardware.profile`` envelope.

الملف الشخصي للعتاد — بيانات نظام تُحفظ على القرص، لا ذاكرة نموذج.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROFILE_SCHEMA = "nexus.hardware.profile"
PROFILE_VERSION = 1
PROFILE_FILENAME = "hardware_profile.json"

#: The twelve §4.1 detection targets, verbatim.
SCAN_TARGETS: tuple[str, ...] = (
    "CPU",
    "GPU",
    "VRAM",
    "RAM",
    "Storage",
    "Displays",
    "Resolution",
    "Windows",
    "Network",
    "Devices",
    "Installed software",
    "Processes",
)


class ProfileError(Exception):
    """Invalid or unreadable hardware profile record."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def _mb(value: Any) -> int | None:
    """Coerce a best-effort megabyte value (None stays None)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProfileError(f"invalid megabyte value {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value.strip())
    raise ProfileError(f"invalid megabyte value {value!r}")


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProfileError(f"invalid integer value {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value.strip())
    raise ProfileError(f"invalid integer value {value!r}")


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


# ------------------------------------------------------------------ entries


@dataclass(slots=True)
class CpuInfo:
    name: str | None
    arch: str | None
    physical_cores: int | None
    logical_cores: int | None
    max_clock_mhz: int | None


@dataclass(slots=True)
class GpuInfo:
    name: str
    vendor: str | None = None
    vram_mb: int | None = None
    driver_version: str | None = None


@dataclass(slots=True)
class MemoryInfo:
    total_mb: int
    available_mb: int | None = None


@dataclass(slots=True)
class StorageVolume:
    mount: str
    kind: str | None = None
    total_mb: int | None = None
    free_mb: int | None = None


@dataclass(slots=True)
class DisplayInfo:
    name: str | None
    width: int
    height: int


@dataclass(slots=True)
class WindowsInfo:
    version: str
    build: str | None = None
    edition: str | None = None
    release: str | None = None
    arch: str | None = None


@dataclass(slots=True)
class NetworkInfo:
    hostname: str
    adapters: list[dict[str, str | None]] = field(default_factory=list)


@dataclass(slots=True)
class DeviceEntry:
    name: str
    status: str | None = None


@dataclass(slots=True)
class SoftwareEntry:
    name: str
    version: str | None = None


@dataclass(slots=True)
class ProcessEntry:
    pid: int
    name: str


# ------------------------------------------------------------------ profile


@dataclass(slots=True)
class HardwareProfile:
    """One full snapshot of the machine (Spec §89 categories)."""

    scanned_at: datetime = field(default_factory=utc_now)
    scanner_kind: str = "unknown"
    cpu: CpuInfo | None = None
    gpus: list[GpuInfo] = field(default_factory=list)
    ram: MemoryInfo | None = None
    storage: list[StorageVolume] = field(default_factory=list)
    displays: list[DisplayInfo] = field(default_factory=list)
    windows: WindowsInfo | None = None
    network: NetworkInfo | None = None
    devices: list[DeviceEntry] = field(default_factory=list)
    installed_software: list[SoftwareEntry] = field(default_factory=list)
    processes: list[ProcessEntry] = field(default_factory=list)

    # ---------------------------------------------------------- helpers

    @property
    def total_vram_mb(self) -> int | None:
        """Sum of known GPU VRAM (None when no GPU reports it)."""
        known = [gpu.vram_mb for gpu in self.gpus if gpu.vram_mb is not None]
        return sum(known) if known else None

    @property
    def max_vram_mb(self) -> int | None:
        """Largest single-GPU VRAM (the model-placement capacity)."""
        known = [gpu.vram_mb for gpu in self.gpus if gpu.vram_mb is not None]
        return max(known) if known else None

    @property
    def logical_cores(self) -> int | None:
        return self.cpu.logical_cores if self.cpu else None

    @property
    def total_ram_mb(self) -> int | None:
        return self.ram.total_mb if self.ram else None

    def primary_storage(self) -> StorageVolume | None:
        return self.storage[0] if self.storage else None

    # ---------------------------------------------------- serialization

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe record (envelope + every Spec §89 category)."""
        return {
            "schema": PROFILE_SCHEMA,
            "schema_version": PROFILE_VERSION,
            "scanned_at": self.scanned_at.isoformat(),
            "scanner_kind": self.scanner_kind,
            "cpu": {
                "name": self.cpu.name,
                "arch": self.cpu.arch,
                "physical_cores": self.cpu.physical_cores,
                "logical_cores": self.cpu.logical_cores,
                "max_clock_mhz": self.cpu.max_clock_mhz,
            }
            if self.cpu
            else None,
            "gpus": [
                {
                    "name": gpu.name,
                    "vendor": gpu.vendor,
                    "vram_mb": gpu.vram_mb,
                    "driver_version": gpu.driver_version,
                }
                for gpu in self.gpus
            ],
            "ram": {
                "total_mb": self.ram.total_mb,
                "available_mb": self.ram.available_mb,
            }
            if self.ram
            else None,
            "storage": [
                {
                    "mount": volume.mount,
                    "kind": volume.kind,
                    "total_mb": volume.total_mb,
                    "free_mb": volume.free_mb,
                }
                for volume in self.storage
            ],
            "displays": [
                {"name": display.name, "width": display.width, "height": display.height}
                for display in self.displays
            ],
            "windows": {
                "version": self.windows.version,
                "build": self.windows.build,
                "edition": self.windows.edition,
                "release": self.windows.release,
                "arch": self.windows.arch,
            }
            if self.windows
            else None,
            "network": {
                "hostname": self.network.hostname,
                "adapters": [dict(adapter) for adapter in self.network.adapters],
            }
            if self.network
            else None,
            "devices": [
                {"name": device.name, "status": device.status}
                for device in self.devices
            ],
            "installed_software": [
                {"name": entry.name, "version": entry.version}
                for entry in self.installed_software
            ],
            "processes": [
                {"pid": process.pid, "name": process.name}
                for process in self.processes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HardwareProfile:
        """Rebuild a profile from its record (missing categories are
        best-effort empty)."""
        if data.get("schema") != PROFILE_SCHEMA:
            raise ProfileError(f"not a {PROFILE_SCHEMA} record")
        cpu_raw = data.get("cpu")
        ram_raw = data.get("ram")
        win_raw = data.get("windows")
        net_raw = data.get("network")
        return cls(
            scanned_at=_parse_dt(data.get("scanned_at")),
            scanner_kind=str(data.get("scanner_kind", "unknown")),
            cpu=CpuInfo(
                name=_opt_str(cpu_raw.get("name")) if cpu_raw else None,
                arch=_opt_str(cpu_raw.get("arch")) if cpu_raw else None,
                physical_cores=_opt_int(cpu_raw.get("physical_cores"))
                if cpu_raw
                else None,
                logical_cores=_opt_int(cpu_raw.get("logical_cores"))
                if cpu_raw
                else None,
                max_clock_mhz=_opt_int(cpu_raw.get("max_clock_mhz"))
                if cpu_raw
                else None,
            )
            if cpu_raw
            else None,
            gpus=[
                GpuInfo(
                    name=str(gpu.get("name")),
                    vendor=_opt_str(gpu.get("vendor")),
                    vram_mb=_mb(gpu.get("vram_mb")),
                    driver_version=_opt_str(gpu.get("driver_version")),
                )
                for gpu in data.get("gpus", [])
                if gpu.get("name")
            ],
            ram=MemoryInfo(
                total_mb=_mb(ram_raw.get("total_mb")) or 0,
                available_mb=_mb(ram_raw.get("available_mb")),
            )
            if ram_raw and _mb(ram_raw.get("total_mb"))
            else None,
            storage=[
                StorageVolume(
                    mount=str(volume.get("mount")),
                    kind=_opt_str(volume.get("kind")),
                    total_mb=_mb(volume.get("total_mb")),
                    free_mb=_mb(volume.get("free_mb")),
                )
                for volume in data.get("storage", [])
                if volume.get("mount")
            ],
            displays=[
                DisplayInfo(
                    name=_opt_str(display.get("name")),
                    width=_opt_int(display.get("width")) or 0,
                    height=_opt_int(display.get("height")) or 0,
                )
                for display in data.get("displays", [])
            ],
            windows=WindowsInfo(
                version=str(win_raw.get("version")),
                build=_opt_str(win_raw.get("build")),
                edition=_opt_str(win_raw.get("edition")),
                release=_opt_str(win_raw.get("release")),
                arch=_opt_str(win_raw.get("arch")),
            )
            if win_raw
            else None,
            network=NetworkInfo(
                hostname=str(net_raw.get("hostname")),
                adapters=[dict(adapter) for adapter in net_raw.get("adapters", [])],
            )
            if net_raw
            else None,
            devices=[
                DeviceEntry(
                    name=str(device.get("name")),
                    status=_opt_str(device.get("status")),
                )
                for device in data.get("devices", [])
                if device.get("name")
            ],
            installed_software=[
                SoftwareEntry(
                    name=str(entry.get("name")),
                    version=_opt_str(entry.get("version")),
                )
                for entry in data.get("installed_software", [])
                if entry.get("name")
            ],
            processes=[
                ProcessEntry(
                    pid=_opt_int(process.get("pid")) or 0,
                    name=str(process.get("name")),
                )
                for process in data.get("processes", [])
                if process.get("pid") is not None
            ],
        )

    def copy(self) -> HardwareProfile:
        """Independent copy (round-trip through the record format)."""
        return HardwareProfile.from_dict(self.to_dict())


def _parse_dt(value: Any) -> datetime:
    if value is None:
        return utc_now()
    return datetime.fromisoformat(str(value))


# -------------------------------------------------------------- persistence


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())  # survive power loss before the rename
    os.replace(tmp_path, path)


def profile_path(data_dir: str | Path) -> Path:
    """Canonical profile location under the runtime ``data`` dir —
    *system data on disk*, never model memory (Plan §4.2)."""
    return Path(data_dir) / PROFILE_FILENAME


def save_profile(profile: HardwareProfile, data_dir: str | Path) -> Path:
    """Persist the profile atomically; returns its path."""
    path = profile_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, profile.to_dict())
    return path


def load_profile(data_dir: str | Path) -> HardwareProfile:
    """Load the persisted profile (ProfileError when absent/corrupt)."""
    path = profile_path(data_dir)
    if not path.is_file():
        raise ProfileError(f"no hardware profile at {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise ProfileError(f"failed to read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path}: expected a JSON object")
    return HardwareProfile.from_dict(data)


def try_load_profile(data_dir: str | Path) -> HardwareProfile | None:
    """Load when present; None otherwise (boot stays scan-free)."""
    try:
        return load_profile(data_dir)
    except ProfileError:
        return None


def make_profile(
    *,
    scanner_kind: str,
    cpu: CpuInfo | None = None,
    gpus: Iterable[GpuInfo] = (),
    ram: MemoryInfo | None = None,
    storage: Iterable[StorageVolume] = (),
    displays: Iterable[DisplayInfo] = (),
    windows: WindowsInfo | None = None,
    network: NetworkInfo | None = None,
    devices: Iterable[DeviceEntry] = (),
    installed_software: Iterable[SoftwareEntry] = (),
    processes: Iterable[ProcessEntry] = (),
) -> HardwareProfile:
    """Assemble a profile (harness / static-scanner convenience)."""
    return HardwareProfile(
        scanner_kind=scanner_kind,
        cpu=cpu,
        gpus=list(gpus),
        ram=ram,
        storage=list(storage),
        displays=list(displays),
        windows=windows,
        network=network,
        devices=list(devices),
        installed_software=list(installed_software),
        processes=list(processes),
    )
