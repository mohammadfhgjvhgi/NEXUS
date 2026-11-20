"""Hardware Change Detection (Final Build Plan §4.3 / Spec §295).

Compares **previous profile vs current profile** and reports, per
the plan's list:

* RAM changed
* GPU changed
* Storage changed
* display changed
* drivers/runtime changes where detectable (GPU driver versions,
  Windows build/release, installed software set)

Spec §295 turns a detected change into: Detect → Reprofile →
Update model catalog → Update resource policy. This module owns the
*Detect* step; the ResourceManager's ``refresh_profile`` chains it
with re-profiling, and later phases (Model Manager) consume the
diff to update their catalogs.

كشف التغيّر — مقارنة الملفين السابق والحالي، و«drivers/runtime where
detectable» تعني أن الفئات غير القابلة للرصد لا تُخترع أبدًا.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from .profile import DisplayInfo, GpuInfo, HardwareProfile, StorageVolume

#: The §4.3 detection categories, verbatim labels.
CHANGE_CATEGORIES: tuple[str, ...] = (
    "ram",
    "gpu",
    "storage",
    "display",
    "drivers",
    "runtime",
)


class ChangeKind:
    """How one category changed."""

    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class HardwareChange:
    """One detected difference between two profiles."""

    category: str  # §4.3 label: ram · gpu · storage · display · drivers · runtime
    kind: str  # added | removed | changed
    detail: str  # human-readable before → after
    major: bool = False  # capacity-affecting (RAM/GPU/VRAM/storage/display)


@dataclass(frozen=True, slots=True)
class HardwareDiff:
    """Outcome of one previous-vs-current comparison."""

    changes: tuple[HardwareChange, ...]
    previous_scanned_at: datetime | None
    current_scanned_at: datetime
    fingerprint_previous: str
    fingerprint_current: str

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)

    def categories(self) -> list[str]:
        return sorted({change.category for change in self.changes})

    def by_category(self, category: str) -> tuple[HardwareChange, ...]:
        return tuple(
            change for change in self.changes if change.category == category
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "has_changes": self.has_changes,
            "categories": self.categories(),
            "changes": [
                {
                    "category": change.category,
                    "kind": change.kind,
                    "detail": change.detail,
                    "major": change.major,
                }
                for change in self.changes
            ],
            "previous_scanned_at": self.previous_scanned_at.isoformat()
            if self.previous_scanned_at
            else None,
            "current_scanned_at": self.current_scanned_at.isoformat(),
            "fingerprint_previous": self.fingerprint_previous,
            "fingerprint_current": self.fingerprint_current,
        }


# ------------------------------------------------------------- fingerprint


def _identity(profile: HardwareProfile) -> dict[str, object]:
    """Stable hardware identity — volatile categories (software,
    devices, processes) are excluded on purpose."""
    return {
        "cpu": {
            "name": profile.cpu.name if profile.cpu else None,
            "physical_cores": profile.cpu.physical_cores if profile.cpu else None,
            "logical_cores": profile.logical_cores,
        },
        "gpus": sorted(
            (gpu.name, gpu.vram_mb) for gpu in profile.gpus
        ),
        "ram_total_mb": profile.total_ram_mb,
        "storage": sorted(
            (volume.mount, volume.total_mb) for volume in profile.storage
        ),
        "displays": sorted(
            (display.width, display.height) for display in profile.displays
        ),
        "windows": {
            "version": profile.windows.version if profile.windows else None,
            "build": profile.windows.build if profile.windows else None,
        },
        "hostname": profile.network.hostname if profile.network else None,
    }


def profile_fingerprint(profile: HardwareProfile) -> str:
    """Stable identity hash (first 16 hex of SHA-256)."""
    payload = repr(sorted(_identity(profile).items())).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ------------------------------------------------------------------- diff


def _gpu_key(gpu: GpuInfo) -> tuple[str, int | None]:
    return (gpu.name, gpu.vram_mb)


def _volume_key(volume: StorageVolume) -> tuple[str, int | None]:
    return (volume.mount, volume.total_mb)


def _display_key(display: DisplayInfo) -> tuple[int, int]:
    return (display.width, display.height)


def _diff_list(
    previous_items: list,
    current_items: list,
    key,
    label: str,
    category: str,
    major: bool,
) -> list[HardwareChange]:
    changes: list[HardwareChange] = []
    prev_keys = {key(item) for item in previous_items}
    current_keys = {key(item) for item in current_items}
    for removed in sorted(prev_keys - current_keys, key=repr):
        changes.append(
            HardwareChange(
                category=category,
                kind=ChangeKind.REMOVED,
                detail=f"{label} removed: {removed!r}",
                major=major,
            )
        )
    for added in sorted(current_keys - prev_keys, key=repr):
        changes.append(
            HardwareChange(
                category=category,
                kind=ChangeKind.ADDED,
                detail=f"{label} added: {added!r}",
                major=major,
            )
        )
    return changes


def diff_profiles(
    previous: HardwareProfile, current: HardwareProfile
) -> HardwareDiff:
    """Compare two profiles (§4.3 — the five listed changes plus
    cpu/network honesty where they differ)."""
    changes: list[HardwareChange] = []

    # RAM changed
    prev_ram = previous.total_ram_mb
    cur_ram = current.total_ram_mb
    if prev_ram != cur_ram:
        changes.append(
            HardwareChange(
                category="ram",
                kind=ChangeKind.CHANGED,
                detail=f"RAM total {prev_ram} MB → {cur_ram} MB",
                major=True,
            )
        )

    # GPU changed (identity + VRAM)
    changes.extend(
        _diff_list(
            previous.gpus, current.gpus, _gpu_key, "GPU", "gpu", major=True
        )
    )

    # drivers changed (same GPU, different driver)
    prev_drivers = {gpu.name: gpu.driver_version for gpu in previous.gpus}
    cur_drivers = {gpu.name: gpu.driver_version for gpu in current.gpus}
    for name in sorted(set(prev_drivers) & set(cur_drivers)):
        if prev_drivers[name] != cur_drivers[name]:
            changes.append(
                HardwareChange(
                    category="drivers",
                    kind=ChangeKind.CHANGED,
                    detail=(
                        f"driver for {name!r}: "
                        f"{prev_drivers[name]!r} → {cur_drivers[name]!r}"
                    ),
                    major=False,
                )
            )

    # Storage changed
    changes.extend(
        _diff_list(
            previous.storage,
            current.storage,
            _volume_key,
            "storage volume",
            "storage",
            major=True,
        )
    )

    # display changed
    changes.extend(
        _diff_list(
            previous.displays,
            current.displays,
            _display_key,
            "display mode",
            "display",
            major=True,
        )
    )

    # runtime changes where detectable (software set, windows release)
    prev_software = {entry.name for entry in previous.installed_software}
    cur_software = {entry.name for entry in current.installed_software}
    for removed in sorted(prev_software - cur_software)[:12]:
        changes.append(
            HardwareChange(
                category="runtime",
                kind=ChangeKind.REMOVED,
                detail=f"software removed: {removed!r}",
            )
        )
    for added in sorted(cur_software - prev_software)[:12]:
        changes.append(
            HardwareChange(
                category="runtime",
                kind=ChangeKind.ADDED,
                detail=f"software added: {added!r}",
            )
        )
    prev_release = previous.windows.release if previous.windows else None
    cur_release = current.windows.release if current.windows else None
    if prev_release != cur_release and (prev_release or cur_release):
        changes.append(
            HardwareChange(
                category="runtime",
                kind=ChangeKind.CHANGED,
                detail=(
                    f"OS runtime {prev_release!r} → {cur_release!r}"
                ),
            )
        )

    # cpu / network — honest extras beyond the §4.3 list
    prev_cpu = (previous.cpu.name, previous.logical_cores) if previous.cpu else None
    cur_cpu = (current.cpu.name, current.logical_cores) if current.cpu else None
    if prev_cpu != cur_cpu:
        changes.append(
            HardwareChange(
                category="cpu",
                kind=ChangeKind.CHANGED,
                detail=f"CPU {prev_cpu!r} → {cur_cpu!r}",
                major=True,
            )
        )
    prev_host = previous.network.hostname if previous.network else None
    cur_host = current.network.hostname if current.network else None
    if prev_host != cur_host:
        changes.append(
            HardwareChange(
                category="network",
                kind=ChangeKind.CHANGED,
                detail=f"hostname {prev_host!r} → {cur_host!r}",
            )
        )

    return HardwareDiff(
        changes=tuple(changes),
        previous_scanned_at=previous.scanned_at,
        current_scanned_at=current.scanned_at,
        fingerprint_previous=profile_fingerprint(previous),
        fingerprint_current=profile_fingerprint(current),
    )
