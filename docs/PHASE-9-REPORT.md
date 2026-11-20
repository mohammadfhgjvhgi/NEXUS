# PHASE 9 REPORT — Window Manager + Human Parallelism (Build Plan §10 / Spec §60–§63, §154–§155)

> Status: **Complete** · Commit: see `CHANGELOG.md` · Exit criteria: **84/84 + live Windows proofs (PASS)** · CI job: "Phases 1–9"
>
> الهوية: «أنت تستخدم جهازك وNEXUS يعمل في مكان آخر في نفس الوقت» —
> الملكية لكل نافذة لا لكل حركة ماوس (Spec §62)، والطبقة العائمة
> شفافة وبسيطة كما وُصفت حرفيًا.

## 1. ما بُني (What landed)

```
nexus/windows/                   ← §10 the Window Manager (NEXUS-owned, stdlib)
├── __init__.py                  exports · WINDOWS_SECTIONS
├── registry.py                  §10.1 the nine-field Window Registry
├── ownership.py                 §10.2 USER / NEXUS / SHARED rules + claims
├── arbitration.py               §10.3 per-window verdicts + the veto hook
├── monitors.py                  §10.4 monitor topology + window placement
├── overlay.py                   §10.5 the native ctypes overlay window
└── manager.py                   the §10 composer over the §9.1 Computer API

nexus/tools/native/              ← additive operation growth (no new records)
├── windows.py                   + geometry (GetWindowRect·MonitorFromWindow·IsIconic)
│                                  + move (SetWindowPos, SWP_NOZORDER|SWP_NOACTIVATE)
│                                  + list_windows rows now carry pid·process·rect·minimized
└── screen.py                    + monitors (EnumDisplayMonitors·GetMonitorInfoW — risk 1)

nexus/core/config/
├── schema.py                    ToolsConfig.windows_enabled (additive, default true)
└── runtime.py                   NexusRuntime.window_manager + hook registration + shutdown

tests/phase09/
├── verify_exit_criteria.py      84/84 (A·B·C·D·E·F) + regressions 1–8
└── live_proof.py                the five §10 proofs ON the real machine
```

### §10.1 Window Registry — `nexus.windows.registry`

Every window NEXUS manages gets the **nine fields, verbatim**:
`window_id · application · task_id · workspace · agent · position ·
size · visibility · input_owner` (plus two documented platform-bridge
fields: `hwnd`, `title`). The registry is *bookkeeping, not a second
aperture*: `ingest()` reconciles the live `windows.list_windows`
rows (which now carry pid · process · rect · minimized) — new
windows open, vanished ones close, survivors get geometry
refreshes. **NEXUS decisions survive the refresh**: ownership and
task bindings are preserved while `update()` *refuses* the
machine-owned fields (position/size/visibility change only via
ingest).

The canonical events `window.opened` / `window.closed` have sat in
the 28-event §2.2 registry since Phase 1 — **this phase is their
first real publisher**. No new event names were invented (the rule
holds).

### §10.2 Window Ownership — `nexus.windows.ownership`

The three-way vocabulary: **USER · NEXUS · SHARED**. Resolution is
assignment → best rule (process/title substring, priority-ordered,
ties stable) → default. The default is **USER** — an unclaimed
window is the human's; NEXUS never assumes input it was not given.
The Spec §61 example ships as the demo ruleset:

```
War Thunder → USER     (title rule)
Chrome A    → USER     (title rule: the human's tab)
Chrome B    → NEXUS    (title rule: the task-tagged window)
PowerPoint  → NEXUS    (process rule)
```

Rules are data — the operator rewrites them per task; `claim()`
stakes a window with the full task binding (`task_id · workspace ·
agent`) so two agents never fight over one window.

### §10.3 Human/AI Input Arbitration — `nexus.windows.arbitration`

Spec §62 is the philosophy: **not** "every user mouse-move pauses
the agent" but **window/input ownership**. Verdicts are per window
and always carry a reason:

| Owner | Verdict |
|---|---|
| USER | **deny** — "human-owned window … NEXUS input denied (Spec §62)" |
| NEXUS | **allow** |
| SHARED | **allow + coordinated** (the caller flags the shared access) |
| unknown | **deny by default** (operator may relax: `unknown_policy="allow"`) |

`as_hook()` turns the arbitrator into a Phase-6 `pre_tool_call`
veto handler — the §7.1/§7.2 seam the Agent Loop already consults.
Only input-bearing tools are arbitrated (**mouse · keyboard · uia ·
windows**); the target window comes from the `hwnd` argument, else
from `x`/`y` coordinates (win32 `WindowFromPoint`), else the call
passes. The runtime installs the hook automatically when the
harness runs. The §8.2 router stays the **only** gate for real
effects — the hook decides whether the loop should even try.

### §10.4 Multiple Monitors — `nexus.windows.monitors`

The §10.4 facts, verbatim: **monitor list · resolution · position ·
window placement**. The live enumeration lives in the §8.3 `screen`
tool (new op `monitors` — `EnumDisplayMonitors` +
`GetMonitorInfoW` with `MONITORINFOEXW`, risk 1, read-only); the
`windows` tool gained `geometry` (GetWindowRect + MonitorFromWindow
+ IsIconic) and `move` (SetWindowPos — routed like every real
effect, mutating op for the §8.2 Scope stage). `MonitorLayout` is
the policy layer over the §9.1 domains: `snapshot()`,
`monitor_for_window()`, `place()` (pure placement math —
center/top-left/bottom-right anchors, work-area clamping, never the
taskbar — CI-testable anywhere).

### §10.5 Overlay — `nexus.windows.overlay`

The Spec §63/§154 box, **verbatim**:

```
┌────────────────────────┐
│ NEXUS is working       │
│ [Pause]  [Resume]      │
└────────────────────────┘
```

شفاف وبسيط: a real Win32 window in **pure ctypes** —
`CreateWindowExW` with `WS_EX_LAYERED | WS_EX_TOPMOST |
WS_EX_TOOLWINDOW` (alpha 235 for the transparent feel, never
click-through), GDI paint (dark field, green/amber state bar, the
status line), two real `BUTTON` children whose `WM_COMMAND` clicks
ride home. The message loop lives in a daemon thread; every
cross-thread poke is a `PostMessage` (the one thread-safe seam).
The controller is a platform-neutral state machine
**IDLE → WORKING ⇄ PAUSED** (illegal transitions raise), audits
every transition with from/to/origin, and fires `on_pause` /
`on_resume` callbacks **only on the human button path** — the §155
emergency-control surface. Off win32: the honest headless backend
(records, never fakes a window).

**Overlay window engineering notes** (the bugs the real machine
caught — the Phase-8 lesson repeated and closed):

1. `DefWindowProcW` called without `argtypes` converts a
   pointer-sized `LPARAM` (the WM_NCCREATE `CREATESTRUCT*`,
   e.g. `401338648800`) through the default 32-bit `c_int` →
   `OverflowError` inside the wndproc → ctypes swallows it, returns
   0 → **WM_NCCREATE returns FALSE and the window dies at birth**
   (no crash, no error — the silent killer). Fix: explicit
   `argtypes`/`restype` for `DefWindowProcW` · `PostMessageW` ·
   `CreateWindowExW` · `FindWindowW`. This is the same bug family
   Phase 8 documented for the raw COM `this` pointer.
2. `place()` treated the geometry rect's `(right, bottom)` as
   `(width, height)` — the overlay "moved" by resizing to 930×1026.
   Fix: `_current_geometry()` returns computed `(l, t, w, h)`.
3. A dismissed overlay can be born again: the thread resets its
   handle on exit so `start()` may respawn (register → create →
   loop), verified across two lifecycles in one process.

## 2. التوصيل (Integration)

* `ToolsConfig.windows_enabled` — additive key, default **true**;
  `false` (or computer off) leaves `runtime.window_manager = None`
  — the Phase-8 behavior **byte for byte**.
* `NexusRuntime` builds the manager over the live `ComputerRuntime`
  at wiring time (§0.4 lazy import — no cycle) and registers the
  §10.3 veto on the harness `pre_tool_call` seam when the harness
  runs; `shutdown()` dismisses the overlay first, never raising.
* **No 13th tool record**: the manager is policy and bookkeeping —
  the registry still holds exactly 12 records; the `windows`/`screen`
  tools grew *operations* additively (their §8.1 records updated in
  place: enum, mutating list, verification contracts —
  `geometry`→`json_field`, `monitors`→`json_field`).

## 3. الإثباتات (Evidence — four layers)

1. **Local**: `tests/phase09/verify_exit_criteria.py` —
   **84/84 checks** (A=17 · B=12 · C=15 · D=13 · E=13 · F=14),
   including the event-first-publisher proof, the hook-veto
   integration on the real `HarnessHooks`, the pure placement math,
   the illegal-transition machine, and **Phases 1–8 re-run as
   subprocesses** (98 · 143 · 104 · 106 · 116 · 88 · 88 · 80).
2. **CI** (GitHub, job "Phases 1–9"): the phase09 step beside
   ruff/pyright and the eight prior harnesses.
3. **The real machine** (DESKTOP-46N9B2S · Win10 19045 ·
   Python 3.14.5, via the t1 bridge) — `tests/phase09/live_proof.py`
   **PROOF RESULT: PASS**:
   * §10.1 — **17→16 live windows** synced (the desktop changed
     between runs — the registry tracked it), 17 window.opened
     events, real process names via QueryFullProcessImageNameW
     (`aces.exe` · `chrome.exe` · `Video.UI.exe` …) — *War Thunder
     itself was on screen, the Spec §61 example made flesh*;
   * §10.2 — ownership distribution over the real rows + an
     explicit claim/release round-trip with the full task binding;
   * §10.3 — both verdicts live (NEXUS → allowed, USER → denied)
     **and the pre_tool_call hook vetoed the human's window**
     (`fire() → False`);
   * §10.4 — **two real monitors**: `\\.\DISPLAY1` 1680×1050
     primary at (0,0) + `\\.\DISPLAY5` 1050×1680 portrait at
     (1680,−379) — negative virtual-desktop coordinates honored;
     a real `SetWindowPos` placement of the overlay onto the
     portrait monitor, verified **inside its work area**;
   * §10.5 — the native overlay: `hwnd` found, **appears** (a GDI
     capture of its rect differs from the empty desktop), **state
     repaints** (working → paused pixels differ — proof the buttons
     text/status actually render), paused/resumed/dismissed, and
     the placement round-trip above. Evidence PNGs:
     `M:\NEXUS\proofs\overlay_{empty,working,paused}.png` and the
     JSON report `M:\NEXUS\proofs\phase9_live.json`.
4. **Deployment**: 21/21 files written + SHA-verified on
   `M:\NEXUS` via the t1 bridge (Bearer), marker
   `PHASE9_COMPLETE.txt`.

## 4. جولة المستودعات (Repository Round 6)

**§10 names no external repositories** — the needed primitives
(user32 windowing, GDI, Win32 messaging, EnumDisplayMonitors) are
OS-native, covered by the stdlib-only discipline. The two pattern
references this phase leans on were already absorbed in earlier
rounds: the ECC/Cline hook seam (Round 3) and the windows-harness
input-transport lessons (Round 5). **Round 6 = NEXUS-native by
plan** — zero imports, zero staging clones, the §0.5 rule holds
trivially. Recorded in `docs/REPOSITORY-INTEGRATION.md`.

## 5. Why the phase's architecture is what it is

* **Per-window, never per-motion** (Spec §62): the arbitrator
  consults ownership, not mouse history — the user's War Thunder
  keystrokes never pause the agent, and the agent never types into
  the user's window.
* **Bookkeeping vs. effects**: the registry/ownership/monitors/
  overlay modules produce *decisions and facts*; every real effect
  (move, focus, screenshot) still passes the §8.2 router. The veto
  hook sits on the Phase-6 seam the loop already consults — no
  second choke point was created.
* **The safe default is the human's**: unknown → deny; unmatched →
  USER. NEXUS earns windows by claim or rule, never by assumption.
* **The overlay is a window, not a wallpaper**: real buttons, real
  message loop, real thread pokes — because §155 demands an
  always-available emergency surface, and a static bitmap cannot
  pause anything.
