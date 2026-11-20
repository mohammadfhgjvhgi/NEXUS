"""Resource Manager (Final Build Plan §4.4 / Spec §90–§91).

Tracks, verbatim from §4.4:

    CPU · RAM · GPU · VRAM · Disk · concurrency · model memory ·
    agent count

* **Capacities** come from the persisted :class:`HardwareProfile`
  (§4.2 system data — never model memory).
* **Allocations** are exact and always tracked: per-model memory +
  VRAM, agent registrations, in-flight concurrency slots, background
  work units.
* **Utilization** is best-effort via an injectable sampler.
* **Pressure** = demand/capacity with fixed thresholds; the
  :class:`ResourcePolicyEngine` (§4.5) turns pressures into the
  Spec §92 degradation ladder.

Spec §91 in one line: make sure one task never crashes the machine.

مدير الموارد — يتّبع الثمانية حرفيًا؛ السعة من بيانات النظام، والضغط
نسبة طلب/سعة بعتبات ثابتة.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .changes import HardwareDiff, diff_profiles, profile_fingerprint
from .policies import (
    PressureLevel,
    PressureReading,
    ResourcePolicyDecision,
    ResourcePolicyEngine,
    level_for_ratio,
)
from .profile import HardwareProfile, save_profile, try_load_profile
from .samplers import Utilization, UtilizationSampler, default_sampler
from .scanner import HardwareScanner, default_scanner

logger = logging.getLogger("nexus.resources")

#: The eight §4.4 tracked resources, verbatim.
TRACKED_RESOURCES: tuple[str, ...] = (
    "cpu",
    "ram",
    "gpu",
    "vram",
    "disk",
    "concurrency",
    "model_memory",
    "agent_count",
)


class ResourceError(Exception):
    """Resource-manager misuse (unknown model, negative memory…)."""


@dataclass(slots=True)
class ResourceBudgets:
    """Operating budgets. ``None`` fields fill from the profile
    (defaults documented per field)."""

    ram_mb: int | None = None  # default 75% of total RAM
    vram_mb: int | None = None  # default 90% of the largest GPU VRAM
    model_memory_mb: int | None = None  # default = RAM budget
    disk_free_min_mb: int | None = None  # default 4096 MB
    max_concurrency: int | None = None  # default logical cores
    max_agents: int | None = None  # default 8
    max_background: int | None = None  # default max_concurrency

    def resolved(self, profile: HardwareProfile | None) -> ResourceBudgets:
        """Explicit values win; the rest derive from the profile."""
        total_ram = profile.total_ram_mb if profile else None
        max_vram = profile.max_vram_mb if profile else None
        cores = profile.logical_cores if profile else None
        fallbacks: dict[str, int | None] = {
            "ram_mb": int(total_ram * 0.75) if total_ram else None,
            "vram_mb": int(max_vram * 0.90) if max_vram else None,
            "model_memory_mb": int(total_ram * 0.75) if total_ram else None,
            "disk_free_min_mb": 4096,
            "max_concurrency": cores,
            "max_agents": 8,
            "max_background": cores,
        }
        kwargs: dict[str, int] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is not None:
                kwargs[f.name] = value
            else:
                fallback = fallbacks[f.name]
                if fallback is not None:
                    kwargs[f.name] = fallback
        return ResourceBudgets(**kwargs)

    def to_dict(self) -> dict[str, int | None]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(slots=True)
class ModelAllocation:
    """One loaded model's footprint."""

    name: str
    memory_mb: int
    vram_mb: int = 0


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Point-in-time state of all eight §4.4 resources (audit-ready)."""

    taken_at: datetime
    capacities: dict[str, int | None]
    budgets: dict[str, int | None]
    allocations: dict[str, Any]
    utilization: dict[str, Any]
    ratios: dict[str, float | None]
    pressures: dict[str, PressureReading]

    def to_dict(self) -> dict[str, Any]:
        return {
            "taken_at": self.taken_at.isoformat(),
            "capacities": self.capacities,
            "budgets": self.budgets,
            "allocations": self.allocations,
            "utilization": self.utilization,
            "ratios": {
                key: round(value, 4) if value is not None else None
                for key, value in self.ratios.items()
            },
            "pressures": {
                key: reading.to_dict() for key, reading in self.pressures.items()
            },
        }


class ResourceManager:
    """Tracks the eight §4.4 resources; owns the hardware profile's
    lifecycle (load → refresh → diff → persist, §4.2–§4.3)."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        scanner: HardwareScanner | None = None,
        budgets: ResourceBudgets | None = None,
        sampler: UtilizationSampler | None = None,
        policy_engine: ResourcePolicyEngine | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._scanner = scanner if scanner is not None else default_scanner()
        self._explicit_budgets = budgets or ResourceBudgets()
        self._sampler = sampler if sampler is not None else default_sampler()
        self._policy_engine = (
            policy_engine if policy_engine is not None else ResourcePolicyEngine()
        )
        self._profile = try_load_profile(self._data_dir)
        self._budgets = self._explicit_budgets.resolved(self._profile)
        self._models: dict[str, ModelAllocation] = {}
        self._agents: set[str] = set()
        self._active_concurrency = 0
        self._background_work = 0

    # ------------------------------------------------------ profile (§4.2)

    @property
    def profile(self) -> HardwareProfile | None:
        return self._profile

    @property
    def budgets(self) -> ResourceBudgets:
        return self._budgets

    @property
    def scanner(self) -> HardwareScanner:
        return self._scanner

    def refresh_profile(self) -> HardwareDiff:
        """Scan → compare with the previous profile (§4.3) → persist
        the new one → re-derive budgets. Reprofile = detect + update
        resource policy (Spec §295); model-catalog updates belong to
        the Model Manager phase."""
        current = self._scanner.scan()
        previous = self._profile
        if previous is not None:
            diff = diff_profiles(previous, current)
        else:
            diff = HardwareDiff(
                changes=(),
                previous_scanned_at=None,
                current_scanned_at=current.scanned_at,
                fingerprint_previous="",
                fingerprint_current=profile_fingerprint(current),
            )
        self._profile = current
        save_profile(current, self._data_dir)
        self._budgets = self._explicit_budgets.resolved(current)
        if diff.has_changes:
            logger.info(
                "hardware changed (%s): %s",
                ", ".join(diff.categories()),
                "; ".join(change.detail for change in diff.changes[:6]),
            )
        return diff

    def load_profile(self) -> bool:
        """(Re)load the persisted profile; True when found."""
        profile = try_load_profile(self._data_dir)
        if profile is None:
            return False
        self._profile = profile
        self._budgets = self._explicit_budgets.resolved(profile)
        return True

    # --------------------------------------------------- models (§4.4)

    @property
    def models(self) -> dict[str, ModelAllocation]:
        return dict(self._models)

    @property
    def model_memory_mb(self) -> int:
        return sum(model.memory_mb for model in self._models.values())

    @property
    def model_vram_mb(self) -> int:
        return sum(model.vram_mb for model in self._models.values())

    def load_model(self, name: str, *, memory_mb: int, vram_mb: int = 0) -> bool:
        """Record a model load. Allocation beyond budget is *allowed*
        and surfaces as pressure — degrade, don't deny (Spec §92)."""
        if not name.strip() or memory_mb < 0 or vram_mb < 0:
            raise ResourceError("model name and non-negative memory are required")
        self._models[name] = ModelAllocation(
            name=name, memory_mb=memory_mb, vram_mb=vram_mb
        )
        return True

    def unload_model(self, name: str) -> bool:
        """Record a model unload (degradation ladder step 2)."""
        return self._models.pop(name, None) is not None

    def set_model_memory(
        self, name: str, *, memory_mb: int, vram_mb: int = 0
    ) -> bool:
        """Resize a loaded model's footprint (ladder step 3)."""
        if name not in self._models:
            return False
        self._models[name] = ModelAllocation(
            name=name, memory_mb=memory_mb, vram_mb=vram_mb
        )
        return True

    # --------------------------------------------------- agents (§4.4)

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    def register_agent(self, agent_id: str) -> bool:
        """Register an active agent (True when newly added)."""
        if agent_id in self._agents:
            return False
        self._agents.add(agent_id)
        return True

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent (True when it was present)."""
        if agent_id not in self._agents:
            return False
        self._agents.remove(agent_id)
        return True

    # --------------------------------------------- concurrency (§4.4)

    @property
    def active_concurrency(self) -> int:
        return self._active_concurrency

    @property
    def background_work(self) -> int:
        return self._background_work

    def acquire_concurrency(self) -> bool:
        """Take one in-flight slot. False = saturated: the caller
        backs off — that *is* reduced concurrency (Spec §92)."""
        limit = self._budgets.max_concurrency
        if limit is None or self._active_concurrency < limit:
            self._active_concurrency += 1
            return True
        return False

    def release_concurrency(self) -> None:
        self._active_concurrency = max(self._active_concurrency - 1, 0)

    def begin_background(self, units: int = 1) -> None:
        self._background_work += max(units, 0)

    def end_background(self, units: int = 1) -> None:
        self._background_work = max(self._background_work - max(units, 0), 0)

    # ------------------------------------------------ state + pressure

    def snapshot(self) -> ResourceSnapshot:
        """All eight §4.4 resources in one record."""
        utilization = self._sampler.sample()
        ratios, pressures = self._pressures(utilization)
        return ResourceSnapshot(
            taken_at=datetime.now(UTC),
            capacities=self._capacities(),
            budgets=self._budgets.to_dict(),
            allocations={
                "models": {
                    name: {"memory_mb": model.memory_mb, "vram_mb": model.vram_mb}
                    for name, model in self._models.items()
                },
                "model_memory_mb": self.model_memory_mb,
                "model_vram_mb": self.model_vram_mb,
                "agent_count": self.agent_count,
                "active_concurrency": self._active_concurrency,
                "background_work": self._background_work,
            },
            utilization=utilization.to_dict(),
            ratios=ratios,
            pressures=pressures,
        )

    def pressures(self) -> dict[str, PressureReading]:
        """Current pressure per resource (one utilization sample)."""
        _, pressures = self._pressures(self._sampler.sample())
        return pressures

    def evaluate(self) -> ResourcePolicyDecision:
        """Policy decision for the current state (§4.5)."""
        return self._policy_engine.evaluate(self.snapshot().pressures)

    # -------------------------------------------------------- internals

    def _capacities(self) -> dict[str, int | None]:
        profile = self._profile
        if profile is None:
            return {
                "total_ram_mb": None,
                "total_vram_mb": None,
                "logical_cores": None,
                "storage_volumes": 0,
            }
        return {
            "total_ram_mb": profile.total_ram_mb,
            "total_vram_mb": profile.total_vram_mb,
            "logical_cores": profile.logical_cores,
            "storage_volumes": len(profile.storage),
        }

    def _pressures(
        self, utilization: Utilization
    ) -> tuple[dict[str, float | None], dict[str, PressureReading]]:
        budgets = self._budgets
        profile = self._profile
        ratios: dict[str, float | None] = {}
        readings: dict[str, PressureReading] = {}

        # RAM — conservative: allocations + measured system usage.
        if budgets.ram_mb:
            demand = self.model_memory_mb + (utilization.ram_used_mb or 0)
            ratio = demand / budgets.ram_mb
            ratios["ram"] = ratio
            readings["ram"] = PressureReading(
                "ram",
                level_for_ratio(ratio),
                ratio,
                f"{demand} MB demand / {budgets.ram_mb} MB budget",
            )
        else:
            ratios["ram"] = None

        # VRAM / GPU — from profile capacity; unknown capacity → no
        # reading (nothing detectable is never invented).
        if budgets.vram_mb:
            vram_demand = self.model_vram_mb + (utilization.vram_used_mb or 0)
            vram_ratio = vram_demand / budgets.vram_mb
            ratios["vram"] = vram_ratio
            readings["vram"] = PressureReading(
                "vram",
                level_for_ratio(vram_ratio),
                vram_ratio,
                f"{vram_demand} MB demand / {budgets.vram_mb} MB budget",
            )
            gpu_ratio = self.model_vram_mb / budgets.vram_mb
            ratios["gpu"] = gpu_ratio
            readings["gpu"] = PressureReading(
                "gpu",
                level_for_ratio(gpu_ratio),
                gpu_ratio,
                "GPU pressure derives from VRAM occupancy",
            )
        else:
            ratios["vram"] = None
            ratios["gpu"] = None

        # CPU — worst of measured load and concurrency saturation.
        cpu_candidates: list[float] = []
        if utilization.cpu_percent is not None:
            cpu_candidates.append(utilization.cpu_percent / 100.0)
        if budgets.max_concurrency:
            cpu_candidates.append(
                self._active_concurrency / budgets.max_concurrency
            )
        cpu_ratio = max(cpu_candidates) if cpu_candidates else None
        ratios["cpu"] = cpu_ratio
        readings["cpu"] = PressureReading(
            "cpu",
            level_for_ratio(cpu_ratio),
            cpu_ratio,
            f"cpu={utilization.cpu_percent}%, slots "
            f"{self._active_concurrency}/{budgets.max_concurrency}",
        )

        # Disk — worst volume usage ratio, plus a free-space floor.
        ratios["disk"], disk_reading = self._disk_pressure(budgets, profile)
        readings["disk"] = disk_reading

        # Model memory + agents + concurrency ratios (§4.4 tracking).
        if budgets.model_memory_mb:
            mm_ratio = self.model_memory_mb / budgets.model_memory_mb
            ratios["model_memory"] = mm_ratio
            readings["model_memory"] = PressureReading(
                "model_memory",
                level_for_ratio(mm_ratio),
                mm_ratio,
                f"{self.model_memory_mb} MB model memory / "
                f"{budgets.model_memory_mb} MB budget",
            )
        else:
            ratios["model_memory"] = None
        if budgets.max_agents:
            agent_ratio = self.agent_count / budgets.max_agents
            ratios["agent_count"] = agent_ratio
            readings["agent_count"] = PressureReading(
                "agent_count",
                level_for_ratio(agent_ratio),
                agent_ratio,
                f"{self.agent_count}/{budgets.max_agents} agents",
            )
        else:
            ratios["agent_count"] = None
        ratios["concurrency"] = (
            self._active_concurrency / budgets.max_concurrency
            if budgets.max_concurrency
            else None
        )

        return ratios, readings

    def _disk_pressure(
        self, budgets: ResourceBudgets, profile: HardwareProfile | None
    ) -> tuple[float | None, PressureReading]:
        if not profile or not profile.storage:
            return None, PressureReading(
                "disk", PressureLevel.NONE, None, "no storage volumes in profile"
            )
        worst_ratio = 0.0
        full_volume = False
        below_floor: list[str] = []
        for volume in profile.storage:
            if not volume.total_mb or volume.free_mb is None:
                continue
            used = volume.total_mb - volume.free_mb
            worst_ratio = max(worst_ratio, used / volume.total_mb)
            if volume.free_mb == 0:
                full_volume = True
            elif (
                budgets.disk_free_min_mb
                and volume.free_mb < budgets.disk_free_min_mb
            ):
                below_floor.append(volume.mount)
        level = level_for_ratio(worst_ratio)
        detail = "worst volume usage ratio"
        if full_volume:
            level = PressureLevel.CRITICAL
            detail = "a volume is full"
        elif below_floor:
            level = max(level, PressureLevel.HIGH)
            detail = (
                f"free space below {budgets.disk_free_min_mb} MB on "
                + ", ".join(below_floor)
            )
        return worst_ratio, PressureReading("disk", level, worst_ratio, detail)


def snapshot_of(manager: ResourceManager) -> Mapping[str, Any]:
    """Audit helper: a manager snapshot as a plain mapping."""
    return manager.snapshot().to_dict()
