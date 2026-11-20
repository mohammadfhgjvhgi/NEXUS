#!/usr/bin/env python3
"""Phase 3 verification harness — Final Build Plan §4 Exit Criteria.

Proves Hardware Intelligence + Resource Manager section by section:

* A — Hardware Scanner (§4.1): the twelve detection targets,
       scanner kinds, platform selection, a REAL scan on the
       machine running this harness.
* B — Hardware Profile (§4.2): the typed record, atomic
       persistence, system data (never model memory).
* C — Change Detection (§4.3): RAM/GPU/Storage/display changes +
       drivers/runtime where detectable + fingerprint semantics.
* D — Resource Manager (§4.4): the eight tracked resources,
       budgets from the profile, allocations, snapshot, pressures.
* E — Resource Policies (§4.5): the §4.5 mappings on the Spec §92
       degradation ladder — reduce → unload → switch → context →
       continue. النتيجة: نُبطئ، لا نُفقد المهمة.
* F — Integration + regression: runtime wiring, profile lifecycle
       across restarts, no invented event names, and Phases 1–2
       harnesses still green (98/98 · 143/143).

Run:  python tests/phase03/verify_exit_criteria.py [--root DIR]
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.core.config import NexusRuntime  # noqa: E402
from nexus.events import CANONICAL_EVENTS, EventBus  # noqa: E402
from nexus.resources import (  # noqa: E402
    CHANGE_CATEGORIES,
    DEGRADATION_LADDER,
    PROFILE_FILENAME,
    PROFILE_SCHEMA,
    PROFILE_VERSION,
    SCAN_TARGETS,
    TRACKED_RESOURCES,
    CpuInfo,
    DisplayInfo,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
    NetworkInfo,
    PosixScanner,
    PressureLevel,
    PressureReading,
    ResourceAction,
    ResourceBudgets,
    ResourceError,
    ResourceManager,
    ResourcePolicyEngine,
    SoftwareEntry,
    StaticScanner,
    StaticUtilizationSampler,
    StorageVolume,
    WindowsInfo,
    default_scanner,
    diff_profiles,
    level_for_ratio,
    make_profile,
    profile_fingerprint,
    profile_path,
)
from nexus.resources.scanner import WindowsScanner  # noqa: E402

# --- verbatim expectations from the Final Build Plan -----------------------

#: Plan §4.1 detection targets, verbatim.
PLAN_SCAN_TARGETS = [
    "CPU", "GPU", "VRAM", "RAM", "Storage", "Displays", "Resolution",
    "Windows", "Network", "Devices", "Installed software", "Processes",
]

#: Plan §4.4 tracked resources (code-block words, normalized).
PLAN_TRACKED = [
    "cpu", "ram", "gpu", "vram", "disk",
    "concurrency", "model_memory", "agent_count",
]

#: Spec §92 degradation ladder, verbatim order (Continue is the outcome).
PLAN_LADDER = [
    ResourceAction.REDUCE_CONCURRENCY,
    ResourceAction.UNLOAD_MODEL,
    ResourceAction.SWITCH_MODEL,
    ResourceAction.REDUCE_CONTEXT,
]

#: The principle, verbatim (Plan §4.5 / Spec §92).
PLAN_PRINCIPLE = "نخفض السرعة قبل أن نخسر المهمة"


class Runner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.section = "?"

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        status = "PASS" if condition else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{status}] ({self.section}) {label}{suffix}")
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def summary(self) -> int:
        total = self.passed + self.failed
        print()
        print("=" * 72)
        print(f"PHASE 3 EXIT CRITERIA — {self.passed}/{total} checks passed"
              f" ({self.failed} failed)")
        print("=" * 72)
        return 0 if self.failed == 0 else 1


def make_test_profile(**overrides) -> HardwareProfile:
    """The standard deterministic machine: 8 cores · 16 GB RAM ·
    8 GB VRAM GPU · 512 GB volume · 2560×1440."""
    base = dict(
        scanner_kind="static",
        cpu=CpuInfo(name="Test CPU 8700", arch="x86_64",
                    physical_cores=8, logical_cores=8, max_clock_mhz=3600),
        gpus=[GpuInfo(name="Test GPU 3060", vendor="Test",
                      vram_mb=8192, driver_version="31.0.15.5222")],
        ram=MemoryInfo(total_mb=16384, available_mb=8192),
        storage=[StorageVolume(mount="M:\\", kind="fixed",
                               total_mb=512000, free_mb=204800)],
        displays=[DisplayInfo(name="D1", width=2560, height=1440)],
        windows=WindowsInfo(version="10", build="19045",
                            edition="Windows 10 Pro", release="22H2",
                            arch="AMD64"),
        network=NetworkInfo(hostname="TEST-PC"),
        installed_software=[SoftwareEntry(name="Git", version="2.45")],
        processes=[],
    )
    base.update(overrides)
    return make_profile(**base)


def build_manager(
    base: Path,
    profile: HardwareProfile | None = None,
    *,
    ram_used_mb: int | None = None,
    cpu_percent: float | None = None,
    budgets: ResourceBudgets | None = None,
    refresh: bool = True,
) -> ResourceManager:
    """A manager over a StaticScanner. ``refresh=True`` scans once so
    budgets derive from the profile (the natural first-boot flow)."""
    manager = ResourceManager(
        base / "data",
        scanner=StaticScanner(profile if profile else make_test_profile()),
        sampler=StaticUtilizationSampler(ram_used_mb=ram_used_mb,
                                         cpu_percent=cpu_percent),
        budgets=budgets,
    )
    if refresh:
        manager.refresh_profile()
    return manager


def section_a(runner: Runner) -> None:
    """A — Hardware Scanner (§4.1)."""
    runner.section = "A/§4.1"

    runner.check("twelve §4.1 detection targets, verbatim",
                 list(SCAN_TARGETS) == PLAN_SCAN_TARGETS)
    record = make_test_profile().to_dict()
    runner.check("profile record carries the twelve categories",
                 all(key in record for key in (
                     "cpu", "gpus", "ram", "storage", "displays",
                     "windows", "network", "devices",
                     "installed_software", "processes",
                 ))
                 and all("vram_mb" in gpu for gpu in record["gpus"])
                 and all("width" in display and "height" in display
                         for display in record["displays"]))

    runner.check("scanner kinds labeled (windows/posix/static)",
                 WindowsScanner.kind == "windows"
                 and PosixScanner.kind == "posix"
                 and StaticScanner(make_test_profile()).kind == "static")

    if sys.platform == "win32":
        runner.check("default_scanner selects WindowsScanner on win32",
                     isinstance(default_scanner(), WindowsScanner))
    else:
        runner.check("default_scanner selects PosixScanner off win32",
                     isinstance(default_scanner(), PosixScanner))

    scanner = StaticScanner(make_test_profile())
    first = scanner.scan()
    second = scanner.scan()
    runner.check("StaticScanner deterministic (same fingerprint)",
                 profile_fingerprint(first) == profile_fingerprint(second))
    runner.check("StaticScanner stamps its kind",
                 first.scanner_kind == "static")
    runner.check("StaticScanner never mutates its source",
                 profile_fingerprint(scanner.scan())
                 == profile_fingerprint(first))

    # ---- REAL scan on this very machine (§4.1 proof where it runs)
    real = default_scanner().scan()
    if sys.platform == "win32":
        runner.check("real Windows scan: kind windows",
                     real.scanner_kind == "windows")
        runner.check("real Windows scan: RAM via GlobalMemoryStatusEx",
                     (real.total_ram_mb or 0) > 0)
        runner.check("real Windows scan: volumes enumerated",
                     len(real.storage) >= 1)
        runner.check("real Windows scan: Windows version identified",
                     real.windows is not None and bool(real.windows.version))
        runner.check("real Windows scan: processes enumerated",
                     len(real.processes) >= 1)
        runner.check("real Windows scan: hostname identified",
                     bool(real.network and real.network.hostname))
    else:
        runner.check("real POSIX scan: kind posix",
                     real.scanner_kind == "posix")
        runner.check("real POSIX scan: CPU cores detected",
                     (real.logical_cores or 0) >= 1)
        runner.check("real POSIX scan: RAM total detected",
                     (real.total_ram_mb or 0) >= 1)
        runner.check("real POSIX scan: storage volumes detected",
                     len(real.storage) >= 1)
        runner.check("real POSIX scan: processes enumerated",
                     len(real.processes) >= 1)
        runner.check("real POSIX scan: hostname identified",
                     bool(real.network and real.network.hostname))
        runner.check("real POSIX scan: undetectable categories stay empty "
                     "(never invented)",
                     real.gpus == [] and real.displays == []
                     and real.installed_software == [])


def section_b(runner: Runner, base: Path) -> None:
    """B — Hardware Profile (§4.2)."""
    runner.section = "B/§4.2"

    runner.check("envelope: schema/version/filename",
                 PROFILE_SCHEMA == "nexus.hardware.profile"
                 and PROFILE_VERSION == 1
                 and PROFILE_FILENAME == "hardware_profile.json")

    profile = make_test_profile()
    record = profile.to_dict()
    rebuilt = HardwareProfile.from_dict(record)
    runner.check("to_dict/from_dict round-trip (fingerprint-equal)",
                 profile_fingerprint(rebuilt) == profile_fingerprint(profile))
    runner.check("round-trip keeps GPU VRAM + driver",
                 rebuilt.gpus[0].vram_mb == 8192
                 and rebuilt.gpus[0].driver_version == "31.0.15.5222")
    runner.check("round-trip keeps storage + display resolution",
                 rebuilt.storage[0].total_mb == 512000
                 and (rebuilt.displays[0].width, rebuilt.displays[0].height)
                 == (2560, 1440))
    runner.check("round-trip keeps software set",
                 rebuilt.installed_software[0].name == "Git")

    runner.check("VRAM helpers: total/max",
                 profile.total_vram_mb == 8192
                 and profile.max_vram_mb == 8192)
    no_gpu = make_test_profile(gpus=[])
    runner.check("VRAM helpers: None without GPUs",
                 no_gpu.total_vram_mb is None
                 and no_gpu.max_vram_mb is None)
    runner.check("capacity helpers (cores/RAM/primary storage)",
                 profile.logical_cores == 8
                 and profile.total_ram_mb == 16384
                 and profile.primary_storage().mount == "M:\\")

    # persistence — system data, not model memory
    data_dir = base / "data"
    from nexus.resources import load_profile, save_profile, try_load_profile

    runner.check("try_load: None when absent (boot stays scan-free)",
                 try_load_profile(data_dir) is None)
    path = save_profile(profile, data_dir)
    runner.check("profile persists under data/ (system data, never "
                 "model memory)",
                 path == data_dir / "hardware_profile.json" and path.is_file())
    runner.check("memory dir untouched by the hardware profile",
                 not (base / "memory" / "hardware_profile.json").exists())
    loaded = load_profile(data_dir)
    runner.check("load round-trip (fingerprint-equal)",
                 profile_fingerprint(loaded) == profile_fingerprint(profile))
    runner.check("record is JSON-clean",
                 json.loads(json.dumps(record))["schema"] == PROFILE_SCHEMA)
    bad = base / "bad"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "hardware_profile.json").write_text("{}", encoding="utf-8")
    try:
        load_profile(bad)
        runner.check("corrupt record rejected", False)
    except Exception:
        runner.check("corrupt record rejected", True)


def section_c(runner: Runner) -> None:
    """C — Change Detection (§4.3)."""
    runner.section = "C/§4.3"

    runner.check("§4.3 categories, verbatim labels",
                 list(CHANGE_CATEGORIES)
                 == ["ram", "gpu", "storage", "display", "drivers", "runtime"])

    diff = diff_profiles(make_test_profile(), make_test_profile())
    runner.check("identical profiles → no changes",
                 not diff.has_changes and diff.changes == ())
    runner.check("identical profiles → same fingerprint",
                 diff.fingerprint_previous == diff.fingerprint_current)

    # RAM changed
    ram_changed = diff_profiles(
        make_test_profile(),
        make_test_profile(ram=MemoryInfo(total_mb=32768)),
    )
    ram_changes = ram_changed.by_category("ram")
    runner.check("RAM change detected (major)",
                 len(ram_changes) == 1 and ram_changes[0].major
                 and "16384" in ram_changes[0].detail
                 and "32768" in ram_changes[0].detail)

    # GPU changed (identity + VRAM)
    gpu_diff = diff_profiles(
        make_test_profile(),
        make_test_profile(gpus=[GpuInfo(name="Test GPU 4070",
                                         vram_mb=12288)]),
    )
    runner.check("GPU change detected (removed + added, major)",
                 {c.kind for c in gpu_diff.by_category("gpu")}
                 == {"removed", "added"}
                 and all(c.major for c in gpu_diff.by_category("gpu")))
    vram_diff = diff_profiles(
        make_test_profile(),
        make_test_profile(gpus=[GpuInfo(name="Test GPU 3060",
                                         vram_mb=12288)]),
    )
    runner.check("VRAM change detected as GPU change (major)",
                 vram_diff.by_category("gpu") != ()
                 and all(c.major for c in vram_diff.by_category("gpu")))

    # Storage changed
    storage_diff = diff_profiles(
        make_test_profile(),
        make_test_profile(storage=[
            StorageVolume(mount="M:\\", kind="fixed",
                          total_mb=512000, free_mb=204800),
            StorageVolume(mount="D:\\", kind="fixed",
                          total_mb=2048000, free_mb=1024000),
        ]),
    )
    runner.check("storage volume added detected (major)",
                 any(c.kind == "added" and c.major
                     for c in storage_diff.by_category("storage")))
    storage_swapped = diff_profiles(
        make_test_profile(),
        make_test_profile(storage=[
            StorageVolume(mount="M:\\", kind="fixed",
                          total_mb=1024000, free_mb=409600),
        ]),
    )
    runner.check("storage capacity change detected (major)",
                 storage_swapped.by_category("storage") != ()
                 and all(c.major
                         for c in storage_swapped.by_category("storage")))

    # display changed
    display_diff = diff_profiles(
        make_test_profile(),
        make_test_profile(displays=[DisplayInfo(name="D1",
                                                width=3840, height=2160)]),
    )
    runner.check("display resolution change detected (major)",
                 display_diff.by_category("display") != ()
                 and all(c.major for c in display_diff.by_category("display")))

    # drivers changed (same GPU, new driver) — where detectable
    driver_diff = diff_profiles(
        make_test_profile(),
        make_test_profile(gpus=[GpuInfo(name="Test GPU 3060",
                                         vram_mb=8192,
                                         driver_version="32.0.15.6094")]),
    )
    driver_changes = driver_diff.by_category("drivers")
    runner.check("driver change detected (minor, not capacity)",
                 len(driver_changes) == 1 and not driver_changes[0].major
                 and "31.0.15.5222" in driver_changes[0].detail)

    # runtime changes (software set)
    runtime_diff = diff_profiles(
        make_test_profile(),
        make_test_profile(installed_software=[
            SoftwareEntry(name="Git", version="2.45"),
            SoftwareEntry(name="Blender", version="4.1"),
        ]),
    )
    runtime_changes = runtime_diff.by_category("runtime")
    runner.check("installed software change detected (runtime)",
                 len(runtime_changes) == 1
                 and runtime_changes[0].kind == "added"
                 and "Blender" in runtime_changes[0].detail)
    runner.check("software-only change keeps the hardware fingerprint",
                 runtime_diff.fingerprint_previous
                 == runtime_diff.fingerprint_current)

    # combined diff metadata
    combined = diff_profiles(
        make_test_profile(),
        make_test_profile(ram=MemoryInfo(total_mb=32768)),
    )
    runner.check("diff carries timestamps + both fingerprints",
                 combined.previous_scanned_at is not None
                 and combined.current_scanned_at is not None
                 and combined.fingerprint_previous
                 != combined.fingerprint_current)
    runner.check("diff serializes (to_dict)",
                 set(combined.to_dict()) == {
                     "has_changes", "categories", "changes",
                     "previous_scanned_at", "current_scanned_at",
                     "fingerprint_previous", "fingerprint_current",
                 })


def section_d(runner: Runner, base: Path) -> None:
    """D — Resource Manager (§4.4)."""
    runner.section = "D/§4.4"

    runner.check("eight §4.4 tracked resources, verbatim",
                 list(TRACKED_RESOURCES) == PLAN_TRACKED)

    # budgets from the profile
    manager = build_manager(base / "d1")
    budgets = manager.budgets
    runner.check("RAM budget = 75% of profile total",
                 budgets.ram_mb == 12288)
    runner.check("VRAM budget = 90% of largest GPU",
                 budgets.vram_mb == 7372)
    runner.check("concurrency budget = logical cores",
                 budgets.max_concurrency == 8)
    runner.check("disk free floor default 4096 MB",
                 budgets.disk_free_min_mb == 4096)
    runner.check("model-memory budget defaults to the RAM budget",
                 budgets.model_memory_mb == 12288)
    explicit = build_manager(
        base / "d2", budgets=ResourceBudgets(max_agents=3, ram_mb=8192)
    )
    runner.check("explicit budgets win over profile-derived",
                 explicit.budgets.max_agents == 3
                 and explicit.budgets.ram_mb == 8192
                 and explicit.budgets.vram_mb == 7372)

    # profile lifecycle (§4.2/§4.3 through the manager)
    fresh = build_manager(base / "d3", refresh=False)
    runner.check("no profile before refresh (boot loads, never scans)",
                 fresh.profile is None)
    first_diff = fresh.refresh_profile()
    runner.check("first refresh persists, empty diff, fingerprint set",
                 fresh.profile is not None and not first_diff.has_changes
                 and first_diff.fingerprint_previous == ""
                 and first_diff.fingerprint_current != "")
    runner.check("profile persisted at the canonical path",
                 profile_path(base / "d3" / "data").is_file())
    changed = build_manager(
        base / "d3",
        make_test_profile(ram=MemoryInfo(total_mb=32768)),
        refresh=False,
    )
    second_diff = changed.refresh_profile()
    runner.check("re-scan against persisted profile detects RAM change",
                 any("RAM" in c.detail for c in second_diff.by_category("ram")))

    # model allocations
    models = build_manager(base / "d4")
    models.load_model("qwen-7b", memory_mb=4800, vram_mb=4500)
    models.load_model("embed", memory_mb=300)
    runner.check("model memory + VRAM tracked",
                 models.model_memory_mb == 5100
                 and models.model_vram_mb == 4500)
    runner.check("unload removes the footprint",
                 models.unload_model("embed")
                 and models.model_memory_mb == 4800)
    runner.check("unload of unknown model returns False",
                 not models.unload_model("ghost"))
    runner.check("set_model_memory resizes",
                 models.set_model_memory("qwen-7b", memory_mb=4000,
                                         vram_mb=4000)
                 and models.model_vram_mb == 4000)
    try:
        models.load_model("bad", memory_mb=-1)
        runner.check("negative memory rejected", False)
    except ResourceError:
        runner.check("negative memory rejected", True)

    # agents + concurrency + background
    tracker = build_manager(base / "d5")
    tracker.register_agent("agent-1")
    tracker.register_agent("agent-1")
    runner.check("agent registration dedupes",
                 tracker.agent_count == 1)
    tracker.register_agent("agent-2")
    runner.check("unregister removes",
                 tracker.unregister_agent("agent-1")
                 and tracker.agent_count == 1
                 and not tracker.unregister_agent("ghost"))
    acquired = [tracker.acquire_concurrency() for _ in range(9)]
    runner.check("concurrency slots: 8 granted then saturated",
                 sum(1 for a in acquired if a) == 8
                 and tracker.active_concurrency == 8)
    tracker.release_concurrency()
    runner.check("release frees a slot",
                 tracker.active_concurrency == 7
                 and tracker.acquire_concurrency())
    tracker.end_background(5)
    tracker.begin_background(3)
    runner.check("background work tracked, floor at zero",
                 tracker.background_work == 3)

    # snapshot: all eight resources
    snap = tracker.snapshot()
    runner.check("snapshot ratios cover all eight tracked resources",
                 set(snap.ratios) == set(PLAN_TRACKED))
    runner.check("snapshot pressures present for measurable resources",
                 {"cpu", "ram", "gpu", "vram", "disk", "model_memory",
                  "agent_count"} <= set(snap.pressures))
    runner.check("snapshot serializes to JSON",
                 json.dumps(snap.to_dict()) is not None)

    # pressure math — deterministic
    p_manager = build_manager(base / "d6", ram_used_mb=1024)
    p_manager.load_model("m", memory_mb=9600)
    ratio = p_manager.snapshot().ratios["ram"]
    runner.check("RAM ratio = (models + measured) / budget",
                 abs(ratio - 10624 / 12288) < 1e-9)
    runner.check("RAM pressure MEDIUM at 0.86",
                 p_manager.snapshot().pressures["ram"].level
                 is PressureLevel.MEDIUM)
    over = build_manager(base / "d7", ram_used_mb=1024)
    over.load_model("m", memory_mb=13000)
    runner.check("over-budget RAM → CRITICAL",
                 over.snapshot().pressures["ram"].level
                 is PressureLevel.CRITICAL)

    # VRAM pressures + unknown capacity
    vram_manager = build_manager(base / "d8")
    vram_manager.load_model("v", memory_mb=500, vram_mb=6500)
    runner.check("VRAM MEDIUM at 0.88 → policy-ready",
                 vram_manager.snapshot().pressures["vram"].level
                 is PressureLevel.MEDIUM)
    no_gpu = make_test_profile(gpus=[])
    gpuless = build_manager(base / "d9", no_gpu)
    gpuless.load_model("v", memory_mb=500, vram_mb=100)
    gpuless_snap = gpuless.snapshot()
    runner.check("unknown VRAM capacity → no vram pressure invented",
                 gpuless_snap.ratios["vram"] is None
                 and "vram" not in gpuless_snap.pressures
                 and "gpu" not in gpuless_snap.pressures)

    # CPU pressure from saturation (utilization unknown)
    cpu_manager = build_manager(base / "d10")
    for _ in range(7):
        cpu_manager.acquire_concurrency()
    runner.check("CPU pressure MEDIUM at 7/8 slots",
                 cpu_manager.snapshot().pressures["cpu"].level
                 is PressureLevel.MEDIUM)

    # disk pressure ladder
    full = make_test_profile(storage=[
        StorageVolume(mount="M:\\", kind="fixed",
                      total_mb=512000, free_mb=0)])
    disk_full = build_manager(base / "d11", full)
    runner.check("full volume → disk CRITICAL",
                 disk_full.snapshot().pressures["disk"].level
                 is PressureLevel.CRITICAL)
    low_free = make_test_profile(storage=[
        StorageVolume(mount="M:\\", kind="fixed",
                      total_mb=512000, free_mb=3000)])
    disk_low = build_manager(base / "d12", low_free)
    runner.check("free below floor → disk HIGH",
                 disk_low.snapshot().pressures["disk"].level
                 is PressureLevel.HIGH)

    # level thresholds (documentation-locked)
    runner.check("pressure thresholds: 0.69/0.70/0.85/0.95/1.0/1.01",
                 level_for_ratio(0.69) is PressureLevel.NONE
                 and level_for_ratio(0.70) is PressureLevel.LOW
                 and level_for_ratio(0.85) is PressureLevel.MEDIUM
                 and level_for_ratio(0.95) is PressureLevel.HIGH
                 and level_for_ratio(1.0) is PressureLevel.HIGH
                 and level_for_ratio(1.01) is PressureLevel.CRITICAL)


def section_e(runner: Runner) -> None:
    """E — Resource Policies (§4.5)."""
    runner.section = "E/§4.5"

    engine = ResourcePolicyEngine()

    runner.check("Spec §92 ladder, verbatim order",
                 list(DEGRADATION_LADDER) == PLAN_LADDER)

    def reading(resource: str, ratio: float) -> PressureReading:
        return PressureReading(resource, level_for_ratio(ratio), ratio,
                               f"test {resource}")

    calm = engine.evaluate({})
    runner.check("no pressure → no actions, full speed",
                 not calm.degraded and calm.actions == ()
                 and "full speed" in calm.summary)
    runner.check("decision always continues (never abandons)",
                 calm.always_continue)

    # §4.5 verbatim: RAM pressure → reduce concurrency
    ram_decision = engine.evaluate({"ram": reading("ram", 0.88)})
    runner.check("RAM pressure → reduce concurrency",
                 [a.action for a in ram_decision.actions]
                 == [ResourceAction.REDUCE_CONCURRENCY])
    ram_high = engine.evaluate({"ram": reading("ram", 0.97)})
    runner.check("RAM HIGH adds unload model",
                 [a.action for a in ram_high.actions]
                 == [ResourceAction.REDUCE_CONCURRENCY,
                     ResourceAction.UNLOAD_MODEL])
    ram_critical = engine.evaluate({"ram": reading("ram", 1.05)})
    runner.check("RAM CRITICAL adds reduce context (ladder step 4)",
                 ResourceAction.REDUCE_CONTEXT
                 in [a.action for a in ram_critical.actions])

    # §4.5 verbatim: VRAM pressure → unload model / switch
    vram_medium = engine.evaluate({"vram": reading("vram", 0.88)})
    runner.check("VRAM pressure → switch model",
                 [a.action for a in vram_medium.actions]
                 == [ResourceAction.SWITCH_MODEL])
    vram_high = engine.evaluate({"vram": reading("vram", 0.97)})
    runner.check("VRAM HIGH → unload before switch (ladder order)",
                 [a.action for a in vram_high.actions]
                 == [ResourceAction.UNLOAD_MODEL,
                     ResourceAction.SWITCH_MODEL])

    # §4.5 verbatim: CPU pressure → reduce background work
    cpu_decision = engine.evaluate({"cpu": reading("cpu", 0.88)})
    runner.check("CPU pressure → reduce background work",
                 [a.action for a in cpu_decision.actions]
                 == [ResourceAction.REDUCE_BACKGROUND])

    # extensions (documented): disk + model memory
    disk_decision = engine.evaluate({"disk": reading("disk", 0.97)})
    runner.check("disk pressure HIGH → reduce background",
                 [a.action for a in disk_decision.actions]
                 == [ResourceAction.REDUCE_BACKGROUND])
    mm_decision = engine.evaluate(
        {"model_memory": reading("model_memory", 0.88)}
    )
    runner.check("model-memory pressure → unload model",
                 [a.action for a in mm_decision.actions]
                 == [ResourceAction.UNLOAD_MODEL])

    # combined pressures keep ladder order
    combined = engine.evaluate({
        "vram": reading("vram", 0.97),
        "ram": reading("ram", 0.90),
        "cpu": reading("cpu", 0.90),
    })
    actions = [a.action for a in combined.actions]
    ladder_positions = [PLAN_LADDER.index(a) for a in actions
                        if a in PLAN_LADDER]
    runner.check("combined pressures ordered by the §92 ladder",
                 ladder_positions == sorted(ladder_positions)
                 and len(actions) >= 3)
    runner.check("one recommendation per distinct action (deduped)",
                 len(actions) == len(set(actions)))

    # LOW pressure stays silent
    low = engine.evaluate({"ram": reading("ram", 0.72)})
    runner.check("LOW pressure → no action yet (early-warning only)",
                 not low.degraded and low.actions == ())

    runner.check("principle text carried verbatim",
                 PLAN_PRINCIPLE in combined.principle)
    runner.check("summary lists the pressured resources",
                 "ram=medium" in combined.summary
                 or "vram=high" in combined.summary)
    runner.check("decision serializes (to_dict)",
                 json.dumps(combined.to_dict()) is not None
                 and combined.to_dict()["degraded"] is True)


def section_f(runner: Runner, root: Path) -> None:
    """F — Integration + regression (runtime wiring, restarts, events)."""
    runner.section = "F/§4.1–§4.5"

    bus = EventBus()
    event_names: list[str] = []
    bus.subscribe("*", lambda event: event_names.append(event.name))

    runtime = NexusRuntime.boot(
        root,
        bus=bus,
        hardware_scanner=StaticScanner(make_test_profile()),
    )
    resources = runtime.resource_manager
    runner.check("runtime wires the ResourceManager",
                 isinstance(resources, ResourceManager))
    runner.check("system.started payload reports phase >= 3",
                 any((e.payload.get("phase") or 0) >= 3
                     for e in bus.history_snapshot()
                     if e.name == "system.started"))

    # agents.max_parallel (§2.1) honored as the agent budget
    runner.check("config agents.max_parallel honored as max_agents",
                 resources.budgets.max_agents
                 == runtime.config.agents.max_parallel)

    runner.check("boot loads but never scans (profile None until refresh)",
                 resources.profile is None)
    diff = resources.refresh_profile()
    runner.check("refresh through the runtime persists system data",
                 resources.profile is not None
                 and (root / "data" / PROFILE_FILENAME).is_file()
                 and not diff.has_changes)
    runner.check("resource file lives in data/, not memory/ (§4.2)",
                 not (root / "memory" / "hardware_profile.json").exists())

    resources.load_model("qwen-7b", memory_mb=9600, vram_mb=6500)
    decision = resources.evaluate()
    runner.check("runtime evaluation returns a policy decision",
                 decision.degraded
                 and any(a.action == ResourceAction.SWITCH_MODEL
                         for a in decision.actions))

    runtime.shutdown()

    # ---- restart: the profile survives as system data
    runtime2 = NexusRuntime.boot(root, bus=EventBus())
    runner.check("profile reloads after NEXUS restart (no scan)",
                 runtime2.resource_manager.profile is not None
                 and runtime2.resource_manager.profile.total_ram_mb == 16384)
    runner.check("budgets re-derived from the persisted profile",
                 runtime2.resource_manager.budgets.ram_mb == 12288)
    runtime2.shutdown()

    # ---- no invented event names (§2.2 registry stays authoritative)
    runner.check("no invented events — everything within the 28 registry",
                 set(event_names) <= CANONICAL_EVENTS)

    # ---- regression: earlier phases stay green
    phase01 = subprocess.run(
        [sys.executable,
         str(REPO_ROOT / "tests" / "phase01" / "verify_exit_criteria.py")],
        capture_output=True, text=True, timeout=600,
    )
    runner.check("phase 1 harness still green (98/98)",
                 phase01.returncode == 0 and "98/98" in phase01.stdout)
    phase02 = subprocess.run(
        [sys.executable,
         str(REPO_ROOT / "tests" / "phase02" / "verify_exit_criteria.py")],
        capture_output=True, text=True, timeout=600,
    )
    runner.check("phase 2 harness still green (143/143)",
                 phase02.returncode == 0 and "143/143" in phase02.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="runtime root (default: isolated temp directory)",
    )
    args = parser.parse_args()

    runner = Runner()
    temp_base: str | None = None
    if args.root is None:
        temp_base = tempfile.mkdtemp(prefix="nexus-phase3-")
        base = Path(temp_base)
    else:
        base = Path(args.root).absolute()

    print("NEXUS Phase 3 — verification harness (Final Build Plan §4)")
    print(f"workspace base: {base}")

    try:
        section_a(runner)
        section_b(runner, base)
        section_c(runner)
        section_d(runner, base)
        section_e(runner)
        section_f(runner, base / "runtime-root")
    finally:
        if temp_base is not None:
            shutil.rmtree(temp_base, ignore_errors=True)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
