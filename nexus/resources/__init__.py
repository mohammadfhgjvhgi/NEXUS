"""NEXUS Resource System package (Final Build Plan §4).

Hardware Intelligence + Resource Manager — the machine knows
itself and works within its capacities:

* §4.1 :mod:`.scanner`    — the twelve detection targets (Windows
  system libraries · POSIX procfs · static for harnesses)
* §4.2 :mod:`.profile`    — the persisted ``hardware_profile``
  (system data on disk, never model memory)
* §4.3 :mod:`.changes`    — previous-vs-current diff + fingerprint
* §4.4 :mod:`.manager`    — the eight tracked resources, budgets,
  pressures, snapshots (CPU · RAM · GPU · VRAM · Disk ·
  concurrency · model memory · agent count)
* §4.5 :mod:`.policies`   — the Spec §92 degradation ladder

No new event names: the §2.2 registry (28) stays authoritative;
this package's audit trail is its own records and snapshots.
"""

from .changes import (
    CHANGE_CATEGORIES,
    ChangeKind,
    HardwareChange,
    HardwareDiff,
    diff_profiles,
    profile_fingerprint,
)
from .manager import (
    TRACKED_RESOURCES,
    ModelAllocation,
    ResourceBudgets,
    ResourceError,
    ResourceManager,
    ResourceSnapshot,
)
from .policies import (
    DEGRADATION_LADDER,
    THRESHOLD_CRITICAL,
    THRESHOLD_HIGH,
    THRESHOLD_LOW,
    THRESHOLD_MEDIUM,
    PressureLevel,
    PressureReading,
    RecommendedAction,
    ResourceAction,
    ResourcePolicyDecision,
    ResourcePolicyEngine,
    level_for_ratio,
)
from .profile import (
    PROFILE_FILENAME,
    PROFILE_SCHEMA,
    PROFILE_VERSION,
    SCAN_TARGETS,
    CpuInfo,
    DeviceEntry,
    DisplayInfo,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
    NetworkInfo,
    ProcessEntry,
    ProfileError,
    SoftwareEntry,
    StorageVolume,
    WindowsInfo,
    load_profile,
    make_profile,
    profile_path,
    save_profile,
    try_load_profile,
)
from .samplers import (
    PosixUtilizationSampler,
    StaticUtilizationSampler,
    Utilization,
    UtilizationSampler,
    WindowsUtilizationSampler,
    default_sampler,
)
from .scanner import (
    HardwareScanner,
    PosixScanner,
    StaticScanner,
    WindowsScanner,
    default_scanner,
)

__all__ = [
    "CHANGE_CATEGORIES",
    "DEGRADATION_LADDER",
    "HardwareChange",
    "HardwareDiff",
    "HardwareProfile",
    "HardwareScanner",
    "MemoryInfo",
    "ModelAllocation",
    "NetworkInfo",
    "PosixScanner",
    "PosixUtilizationSampler",
    "PressureLevel",
    "PressureReading",
    "ProcessEntry",
    "PROFILE_FILENAME",
    "PROFILE_SCHEMA",
    "PROFILE_VERSION",
    "ProfileError",
    "RecommendedAction",
    "ResourceAction",
    "ResourceBudgets",
    "ResourceError",
    "ResourceManager",
    "ResourcePolicyDecision",
    "ResourcePolicyEngine",
    "ResourceSnapshot",
    "SCAN_TARGETS",
    "SoftwareEntry",
    "StaticScanner",
    "StaticUtilizationSampler",
    "StorageVolume",
    "THRESHOLD_CRITICAL",
    "THRESHOLD_HIGH",
    "THRESHOLD_LOW",
    "THRESHOLD_MEDIUM",
    "TRACKED_RESOURCES",
    "Utilization",
    "UtilizationSampler",
    "WindowsInfo",
    "WindowsScanner",
    "WindowsUtilizationSampler",
    "CpuInfo",
    "DeviceEntry",
    "DisplayInfo",
    "GpuInfo",
    "ChangeKind",
    "default_sampler",
    "default_scanner",
    "diff_profiles",
    "level_for_ratio",
    "load_profile",
    "make_profile",
    "profile_fingerprint",
    "profile_path",
    "save_profile",
    "try_load_profile",
]
