# PHASE 8 REPORT — Windows Computer Runtime (Build Plan §9 / Spec §41–§45, §71)

> Status: **Complete** · Commit: see `CHANGELOG.md` · Exit criteria: **80/80 + live Windows proofs** · CI job: "Phases 1–8"
>
> الهوية: «NEXUS يستخدم الكمبيوتر الحقيقي» — الواجهة والسلسلة والطبقات الثلاث،
> وكل تأثير حقيقي خلف بوابة §8.2 نفسها.

## 1. ما بُني (What landed)

```
nexus/computer/                  ← §9 the Windows Computer Runtime
├── __init__.py                  register_computer_tools · build_computer_runtime
├── api.py                       §9.1 Computer API — the eight domains
├── hierarchy.py                 §9.5 FallbackChain (5 layers, honest traces)
├── uia_native.py                §9.4 native UIA client (ctypes COM)
├── input_engine.py              §9.2 transports (ADAPT: foreground + message)
└── adapters/
    └── pywinauto_backend.py     §9.3 pywinauto (MODE A «USE», [computer] extra)

nexus/tools/native/
├── _sendinput.py                SendInput packing (shared leaf, explicit widths)
├── mouse.py                     §9.1 mouse tool (risk 3)
├── keyboard.py                  §9.1 keyboard tool (risk 3)
└── uia.py                       §9.1 uia tool (risk 2)
```

### §9.1 Computer API — `nexus.computer.api.ComputerRuntime`

The eight domains, verbatim: **screens · windows · focus · mouse ·
keyboard · clipboard · uia · processes**. Every domain method is a
*thin router client* — `router.route(...)` through the §8.2
seven-stage pipeline (policy → confirmation → scope → resources →
execute → normalise → verify). The Computer API adds **no second
choke point**: it is policy and orchestration; the router stays the
single gate every real-world effect passes through. Canonical
`tool.called/completed/failed` events flow on domain calls — **zero
new event names** (the 28-event rule holds).

The three mechanics records (`mouse` · `keyboard` · `uia`) register
**additively** on the same registry — the §8.3 nine stay untouched
(Phase 7 byte for byte when `tools.computer_enabled = false`).

### §9.5 Fallback Hierarchy — `nexus.computer.hierarchy`

The verbatim order — **Application API → Windows UI Automation →
Browser DOM/Accessibility → Vision → Mouse/Keyboard**. One
coordinator, honest bookkeeping:

* a layer with no provider is *unavailable* by definition — the chain
  degrades to the next layer (that is the point);
* a provider returning `None` = "unsupported for this action" —
  recorded, fall through;
* a raised `LayerError` = "tried and failed" — recorded, fall through
  (the primitive layers catch what the elegant ones drop);
* the first success wins and is stamped with its layer;
* all-fail → `HierarchyError` carrying the **full attempt ledger**.

DOM/a11y and Vision report unavailable until their phases ship —
honest degradation, never stubbed success.

### §9.4 Native UIA — `nexus.computer.uia_native`

A dependency-free **ctypes COM client** for the OS UIA service — the
first layer wherever possible, *before any backend library*:

* `IUIAutomation` — root · `ElementFromHandle` · `GetFocusedElement`
  · `CreateTrueCondition` → `FindAll` children (a bounded BFS with
  `depth ≤ 8`, `max_nodes ≤ 500`);
* `IUIAutomationElement` — `SetFocus` · `CurrentProcessId` ·
  `CurrentControlType` · `CurrentName` · `CurrentIsEnabled` ·
  `CurrentClassName` · `GetCurrentPropertyValue` (the rectangle as an
  r8 SAFEARRAY) · `GetCurrentPattern`;
* patterns — **Invoke** (10000) and **Value** (10002, `SetValue`).

Every HRESULT is checked and raised with its code in hex; BSTRs are
freed, returned SAFEARRAYs destroyed, per-element AddRefs Released,
and COM apartment inits are per-thread and **owned-paired** (an
external MTA is used as-is, never uninitialized by us). Off win32
every probe refuses honestly — the layer never fakes an element.

### §9.2 Transports — `nexus.computer.input_engine` (ADAPT)

Adapted — never imported — from `browser-use/windows-harness`
(`inject.py`/`delivery.py`, MIT, pinned 46a37cf):

* **foreground** — `SetForegroundWindow` (with the
  `AttachThreadInput` assist + input nudge when the OS refuses a bare
  call) then real `SendInput`. Moves the user's cursor — the §9.5
  last resort, and the transport says so;
* **message** — `WM_CHAR` units posted to a specific window
  (never activates). Mouse-by-message is **refused by design**
  (Chromium/WPF/UWP discard posted clicks — pretending otherwise
  would be the silent no-op NEXUS never does);
* `ForegroundError` ≠ `TransportRefusedError` — "could not take the
  foreground" is a different failure than "this platform refuses
  injection", and the error never lies about which one happened.

The SendInput packing (shared leaf `nexus/tools/native/_sendinput.py`)
uses **explicit-width fields** (`c_int32`/`c_uint32`/`c_size_t`) —
the winuser layout stays byte-exact on every platform, not just where
`c_long` happens to be 4 bytes (a real bug the linux run caught:
`sizeof(INPUT)` = 56 with naive `c_long`, = 40 — the winuser truth —
with explicit widths). Unicode typing emits per character *all downs
then all ups* so surrogate pairs decode.

### §9.3 pywinauto — MODE A «USE», the `[computer]` extra

BSD-3-Clause · upstream pinned 18d2a95 · **optional** (`pip install
nexus-core[computer]`): deep UIA control matching, robust waiters,
`type_keys` into a specific control. The discipline:

* imported **lazily inside every method** — a machine without the
  extra keeps every native path working (the harness source-verifies
  no module-level import exists anywhere in `nexus/`);
* the honest probe reports win32 + importable, with the reason;
* every failure wrapped in `BackendError` — no tracebacks leaking.

## 2. التكامل (Integration)

* `build_tool_system(computer=True)` registers the three mechanics
  records **after** the §8.3 nine — the default stays nine-only (the
  Phase-7 direct-call contract, byte for byte); the **runtime** passes
  `tools.computer_enabled` (new additive key, default true) and wires
  `ComputerRuntime` over the live router.
* `NexusRuntime.computer_runtime` property — `None` when disabled
  (the Phase-7 behaviour exactly).
* The §7.1 `pre_tool_call` veto still sits in front (it guards the
  router, hence every computer effect too); the §6.2 loop can drive
  domain calls through its `RoutedToolSink` unchanged.

## 3. الأمان والمخاطر (Security & risk)

| Surface | Risk | Rationale |
|---|---|---|
| `mouse` tool | **3** | moves the user's real cursor into whatever has focus |
| `keyboard` tool | **3** | types as the user into whatever holds focus |
| `uia` tool | **2** | reads UI state (risk 1 semantics) but `invoke`/`set_value`/`focus` mutate UI |
| hierarchy input layer | — | last resort by construction (§9.5 order is the guard) |

The §8.2 risk gate applies per tool: above `tools.confirm_danger_above`
a human confirms, always. The bridge's own remote surface agrees —
its `cu_type_text` / `cu_key_press` / `cu_mouse_move` exist but are
**blocked for remote callers** (gatekeeper); NEXUS's equal stance is
the §8.2 confirmation fold + risk 3.

## 4. الإثبات (Evidence)

* **Local (cross-platform)**: `tests/phase08/verify_exit_criteria.py`
  — **80/80** (A=14 · B=12 · C=12 · D=17 · E=5 · F=20), including the
  §F regression re-run of Phases 1–7 as subprocesses
  (98 · 143 · 104 · 106 · 116 · 88 · 88).
* **CI (GitHub, ubuntu)**: the "Phases 1–8" job — ruff + pyright 0
  (with `pywinauto` installed for the type-checker) + all eight
  harnesses; the textual line from the job log:
  *"verify_exit_criteria.py — 80 passed, 0 failed"*.
* **Real Windows (the operator's box, DESKTOP-46N9B2S · Windows
  10.0.19045 · Python 3.14.5, via the bridge)**:
  * the §9.4 native client read the **focused element** live
    (real name/control-type/process-id);
  * the §9.1 domains returned live evidence — `cu_list_windows`
    real titles (Chrome + the Arabic «إعدادات» window),
    `desktop_screenshot` a real PNG, `ps_get_process` the real table;
  * **the full phase-8 harness ran ON the device itself**
    (`python tests\phase08\verify_exit_criteria.py` on M:\NEXUS) —
    80/80 with the win32 live probes as BONUS;
  * the §9.5 hierarchy answered live: uia×2 providers, input×1,
    application_api/dom_a11y/vision honestly unavailable.
* **Failure/recovery**: crash-injected layers fall through to the
  next (B); refused platforms never fake (C/D); an unservable chain
  raises with the full ledger (B); `computer_enabled=false` restores
  Phase-7 byte for byte (F).

## 5. خريطة الطبقات على المواصفة (Spec mapping)

| Plan §9 | Spec | NEXUS module |
|---|---|---|
| 9.1 Computer API | §41 aperture reuse | `nexus/computer/api.py` |
| 9.2 windows-harness | — | `nexus/computer/input_engine.py` (ADAPT) |
| 9.3 pywinauto | — | `nexus/computer/adapters/pywinauto_backend.py` (MODE A) |
| 9.4 native UIA | — | `nexus/computer/uia_native.py` (ctypes COM) |
| 9.5 fallback hierarchy | — | `nexus/computer/hierarchy.py` |

## 6. ماذا بعد (Next)

PHASE 9 — Browser Automation (Plan §10) عند أمر المشغّل. The DOM/a11y
layer of §9.5 is its docking point: the chain is already waiting.
