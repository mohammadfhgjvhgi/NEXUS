# PHASE 3 — Hardware Intelligence + Resource Manager · Completion Report

> Final Build Plan §4 · Concept locked: **the machine knows itself and works within its capacities**
> المصدر الحاكم: `docs/reference/NEXUS-Final-Build-Plan-v1.0.md` (§4.1–§4.6) + `NEXUS-Master-Technical-Specification-v1.0.md` (§89–§92, §291–§295)

## الملخص التنفيذي

<div dir="rtl">

المرحلة الثالثة تجعل NEXUS **يعرف الجهاز بنفسه**: ماسح عتاد يكتشف الأهداف الاثني عشر (§4.1) عبر مكتبات Windows النظامية فقط (§4.6 — بلا أي مستودع خارجي أو إطار وكيل)، ملف شخصي يُحفظ كـ**بيانات نظام على القرص** لا كذاكرة نموذج (§4.2)، كشف تغيّر يقارن السابق بالحالي (§4.3)، مدير موارد يتّبع الثمانية المطلوبة حرفيًّا (§4.4)، وسياسات تدهور على سلّم المواصفة §92 الحرفي — تقليل التزامن ← إلغاء نموذج خامل ← تبديل لأصغر ← تقليل السياق ← المتابعة — لأن **البطء أفضل من ضياع المهمة** (§4.5). بلا أسماء أحداث جديدة: سجل §2.2 (28) يبقى المصدر الوحيد.

</div>

Phase 3 makes NEXUS **know its machine**: a scanner discovering the twelve §4.1 targets through Windows system libraries only (§4.6 — no external repository, no agent framework), a profile persisted as **system data on disk, never model memory** (§4.2), change detection comparing previous vs current (§4.3), a resource manager tracking the eight §4.4 items verbatim, and degradation policies running the verbatim Spec §92 ladder — *reduce concurrency → unload idle model → switch smaller model → reduce context → continue* — because **slowness is better than losing the task** (§4.5). No new event names: the §2.2 registry (28) stays the single authority.

---

## 1 · Deliverables vs. Plan (مقابل الخطة)

| Plan section | Spec support | Delivered | Location |
|---|---|---|---|
| §4.1 Hardware Scanner | Spec §89 | The **twelve detection targets verbatim** (`CPU GPU VRAM RAM Storage Displays Resolution Windows Network Devices Installed software Processes`). `WindowsScanner`: ctypes (GlobalMemoryStatusEx · GetLogicalDrives/GetDriveTypeW · screen metrics), winreg (CPU name, 64-bit GPU VRAM `qwMemorySize`, edition, uninstall enumeration ×3 hives), PowerShell CIM (processor/GPU+resolutions/network/PnP), tasklist processes. `PosixScanner` (procfs/sysfs), `StaticScanner` (harness), `default_scanner()` platform pick. Every probe best-effort: a failing category degrades to empty — never an exception | `nexus/resources/scanner.py` |
| §4.2 Hardware Profile | Spec §89 | Typed `HardwareProfile` + 10 entry dataclasses, persisted as **`hardware_profile.json` under `NexusPaths.data`** with the §2.5 crash discipline (temp + `os.replace` + `fsync`), envelope `nexus.hardware.profile` v1. System data — never model memory | `nexus/resources/profile.py` |
| §4.3 Change Detection | Spec §295 | `diff_profiles`: RAM/GPU/Storage/display changes (major) + drivers/runtime **where detectable** (GPU driver, OS release, software set — minor), hardware fingerprint (volatile categories excluded: software-only changes keep the fingerprint) | `nexus/resources/changes.py` |
| §4.4 Resource Manager | Spec §90–§91 | Tracks the **eight §4.4 items verbatim** (`cpu ram gpu vram disk concurrency model_memory agent_count`): capacities from the profile, exact allocations (per-model memory/VRAM, agents, concurrency slots, background units), best-effort utilization samplers (injectable), budgets (75% RAM · 90% VRAM · cores · 4096 MB disk floor · `agents.max_parallel` from §2.1 config), pressure ratios + thresholds (LOW 0.70 · MEDIUM 0.85 · HIGH 0.95 · CRITICAL >1.0), JSON snapshots | `nexus/resources/manager.py`, `nexus/resources/samplers.py` |
| §4.5 Resource Policies | Spec §92 | The three §4.5 mappings verbatim (RAM→reduce concurrency · VRAM→unload/switch · CPU→reduce background) on the **Spec §92 ladder verbatim order**; one deduped recommendation per action; the ladder always ends at **Continue** — there is deliberately no abort action; principle carried verbatim | `nexus/resources/policies.py` |
| §4.6 Repo/Reference | — | Honored: Windows APIs/system libraries only; zero external repositories; **no agent framework**; stdlib-only (ctypes/winreg/subprocess/socket) | — |
| Integration | Plan §4 | `NexusRuntime.boot(hardware_scanner=…)` wires the ResourceManager; boot **loads** the persisted profile but never scans (explicit `refresh_profile()`); `agents.max_parallel` honored; payload `phase: 3` | `nexus/core/config/runtime.py` |

## 2 · Exit criteria proof (إثبات معايير الخروج) — `tests/phase03/verify_exit_criteria.py`

**104/104 checks passed (0 failed), exit code 0.** Sections:

| Section | Scope | Checks |
|---|---|---|
| A — Hardware Scanner | §4.1 | **14** (incl. a real scan on the machine running the harness) |
| B — Hardware Profile | §4.2 | **14** |
| C — Change Detection | §4.3 | **14** |
| D — Resource Manager | §4.4 | **33** |
| E — Resource Policies | §4.5 | **17** |
| F — Integration · regression | §4.1–§4.5 | **12** |
| **Total** | | **104** |

Key proofs: the twelve §4.1 targets verbatim; a **real platform scan** (POSIX checks on CI/Linux, six Windows checks activate on the Windows box: RAM via GlobalMemoryStatusEx, volumes, Windows version, processes, hostname); profile persisted under `data/` while `memory/` stays untouched (§4.2); software-only changes keep the fingerprint; RAM ratio math exact (`(models+measured)/budget`); over-budget → CRITICAL; unknown VRAM capacity → no pressure invented; Spec §92 ladder order + dedup; LOW pressure silent; `always_continue`; Phases 1–2 re-run inside §F: **98/98 and 143/143**.

## 3 · Quality gates (بوابات الجودة)

- `ruff check nexus tests` — **All checks passed**
- `pyright` (standard, 3.11) — **0 errors, 0 warnings, 0 informations**
- `tests/phase01` — **98/98** · `tests/phase02` — **143/143** (regressions, also re-run inside §F)
- `tests/phase03` — **104/104**

## 4 · Documented design decisions (قرارات موثقة)

1. **No new event names.** The §2.2 registry (28) is authoritative; the resource component publishes nothing — its audit trail is its own records: snapshots, diffs, decisions. Guarded by a §F check (every published event ∈ the 28).
2. **Profile = system data (§4.2 verbatim).** One JSON record under `NexusPaths.data`; never routed through any memory namespace; the §F harness proves `memory/` stays untouched.
3. **Boot never scans.** Construction only *loads* a persisted profile (fast, and Phase 1/2 boot behavior untouched — their harnesses stay green without a scanner). Discovery is explicit: `refresh_profile()` = scan → diff → persist → re-derive budgets.
4. **§4.6 honored literally.** Windows system libraries only: ctypes, winreg, PowerShell CIM, tasklist — no repositories integrated this phase (helpers stay "later" per the plan); stdlib-only, no agent framework.
5. **Best-effort = never invented.** A category that cannot be detected stays empty (POSIX GPUs/resolutions/software); unknown VRAM capacity yields no pressure reading. Mirrors §4.3's "where detectable".
6. **64-bit VRAM truth.** CIM `AdapterRAM` is uint32 (wraps above 4 GB); the registry's `HardwareInformation.qwMemorySize` (8-byte LE) overrides it when present.
7. **GPU pressure derives from VRAM occupancy** — GPU utilization itself is not stdlib-measurable; documented on the reading.
8. **Conservative RAM demand** = model allocations + measured system usage (degrade early, Spec §92).
9. **Degrade, never deny.** `load_model` beyond budget is allowed and surfaces as pressure; saturated `acquire_concurrency` returns False (the caller backing off *is* reduced concurrency). The policy engine only recommends; there is no abort action — the ladder ends at Continue.
10. **§2.1 config tree untouched.** Resource budgets are programmatic defaults from the hardware profile, with exactly one config hook: `agents.max_parallel` → `max_agents` (both §2.1 and §4.4 honored without extending the six-section verbatim tree).
11. **Fingerprint excludes volatile categories** (software/devices/processes): hardware identity changes when hardware changes; software changes are detected as §4.3 runtime changes without invalidating identity.

## 5 · Inventory (الجرد)

- **Package** — `nexus/resources/`: `profile.py` (§4.2 models + persistence) · `scanner.py` (§4.1, three scanners) · `changes.py` (§4.3 diff + fingerprint) · `manager.py` (§4.4) · `policies.py` (§4.5 + pressure vocabulary) · `samplers.py` (utilization, three samplers) · `__init__.py`
- **Modified** — `nexus/core/config/runtime.py` (wiring + phase payload 3) · `nexus/__init__.py` (0.3.0, NEXUS_PHASE=3) · `tests/phase02/verify_exit_criteria.py` (phase-payload check made forward-compatible `≥ 2`) · `pyproject.toml` (0.3.0)
- **Tests** — `tests/phase03/verify_exit_criteria.py` (A–F, 104 checks, runs Phases 1–2 as subprocesses)
- **Docs** — README roadmap & structure, CHANGELOG, this report, ownership map (`nexus/README.md`)

## 6 · Reproduce (إعادة الإثبات)

```bash
python tests/phase03/verify_exit_criteria.py     # 104/104 + 98/98 + 143/143, exit code 0
python tests/phase01/verify_exit_criteria.py     # 98/98
python tests/phase02/verify_exit_criteria.py     # 143/143
ruff check nexus tests && pyright                # clean
```

On the Windows box the §A block automatically switches to six **real WindowsScanner** proofs (GlobalMemoryStatusEx RAM, enumerated volumes, Windows version, processes, hostname).

---

<div dir="rtl">

**الحكم:** استُوفت أقسام الخطة §4.1–§4.6 حرفيًّا: الأهداف الاثنا عشر نصًّا، والملف بيانات نظام لا ذاكرة نموذج، والثمانية متبوعة نصًّا، وسلّم §92 بترتيبه الحرفي ينتهي دائمًا بالمتابعة. الانتقال إلى **PHASE 4 — Local Model Runtime** (الخطة §5) مُصرَّح به وفق قاعدة الترتيب الإجباري.

</div>

**Verdict:** Plan §4.1–§4.6 satisfied literally — the twelve targets verbatim, the profile as system data (never model memory), the eight tracked resources verbatim, and the Spec §92 ladder in its verbatim order always ending at Continue. Transition to **PHASE 4 — Local Model Runtime** (Plan §5) is authorized under the mandatory build order.
