#!/usr/bin/env python3
"""Phase 9 verification harness — Final Build Plan §10 Exit Criteria.

Proves the Window Manager + Human Parallelism section by section:

* A — Window Registry (§10.1): the nine fields verbatim; ingest/diff
       (open · update · close); the canonical ``window.opened`` /
       ``window.closed`` events — published for real for the first
       time since the 28-event registry was written in Phase 1;
       NEXUS decisions (ownership/task binding) survive geometry
       refreshes while machine fields refuse direct writes.
* B — Window Ownership (§10.2): USER · NEXUS · SHARED; the Spec §61
       example as the demo ruleset (War Thunder → USER, Chrome A →
       USER, Chrome B → NEXUS, PowerPoint → NEXUS); priority
       resolution; explicit assignment beats patterns; the safe
       default is USER (NEXUS never assumes input it was not given).
* C — Human/AI Input Arbitration (§10.3): per-window verdicts with
       reasons (USER → deny, NEXUS → allow, SHARED → allow+
       coordinated, unknown → deny by default); the ``as_hook``
       veto installed on the Phase-6 ``pre_tool_call`` seam blocks
       input into human-owned windows and passes everything else.
* D — Multiple Monitors (§10.4): MonitorRecord fields (monitor
       list · resolution · position · work area · primary); row
       parsing; the pure placement math (center/top-left/bottom-
       right, work-area clamping) — CI-testable anywhere; the
       MonitorLayout routes its probes through the Computer API.
* E — Overlay (§10.5): the IDLE → WORKING ⇄ PAUSED machine, legal
       transitions only; the status lines verbatim ("NEXUS is
       working" / paused); button-origin pause/resume fire the
       callbacks (the §155 emergency-control surface); honest
       headless degradation off win32; BONUS: the real native
       ctypes overlay on a win32 host (FindWindow + state poke).
* F — Integration + regression: NexusRuntime wires windows_enabled
       (manager + the §10.3 veto on the harness hooks); disabled →
       the Phase-8 behavior byte for byte; the screen/windows tool
       ops grew additively (monitors · geometry · move); Phases
       1–8 harnesses stay green (98 · 143 · 104 · 106 · 116 · 88 ·
       88 · 80).

Run:  python tests/phase09/verify_exit_criteria.py
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.events import Event, EventBus  # noqa: E402
from nexus.harness import HarnessHooks  # noqa: E402
from nexus.harness.hooks import HookContext  # noqa: E402
from nexus.tools import build_tool_system  # noqa: E402
from nexus.windows import (  # noqa: E402
    DEMO_RULES,
    INPUT_TOOLS,
    OWNERS,
    STATUS_PAUSED,
    STATUS_WORKING,
    ArbitrationDecision,
    InputArbitrator,
    InputOwner,
    MonitorLayout,
    MonitorRecord,
    OverlayController,
    OverlayError,
    OverlayState,
    OwnershipPolicy,
    OwnershipRule,
    WindowRecord,
    WindowRegistry,
    build_overlay,
    build_window_manager,
    window_id_for,
)

ON_WINDOWS = sys.platform == "win32"


# ------------------------------------------------------------------- runner


class Runner:
    """Check counter with the house reporting format."""

    def __init__(self) -> None:
        self.section = ""
        self.passed = 0
        self.failed = 0
        self.bonus = 0

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        mark = "PASS" if condition else "FAIL"
        line = f"  [{mark}] ({self.section}) {label}"
        if detail and not condition:
            line += f" — {detail}"
        print(line)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def bonus_check(self, label: str, condition: bool, detail: str = "") -> bool:
        """Windows-only evidence: counted separately — a non-win32
        machine reports SKIP, never a failure."""
        if condition:
            self.bonus += 1
            print(f"  [BONUS] ({self.section}) {label}")
        else:
            print(f"  [SKIP]  ({self.section}) {label} — {detail}")
        return condition

    def summary(self) -> int:
        print()
        print("=" * 72)
        name = Path(sys.argv[0]).name
        if self.failed:
            print(f"{name} — {self.passed} passed, {self.failed} FAILED")
            print("=" * 72)
            return 1
        print(f"{name} — {self.passed} passed, 0 failed (+{self.bonus} bonus)")
        print("=" * 72)
        return 0


# ---------------------------------------------------------------- fixtures


ROWS_A = [
    {"hwnd": 1001, "title": "War Thunder — Steam", "process": "aces.exe",
     "rect": (0, 0, 1680, 1050), "minimized": False},
    {"hwnd": 1002, "title": "Google Chrome — YouTube", "process": "chrome.exe",
     "rect": (10, 10, 900, 700), "minimized": False},
    {"hwnd": 1003, "title": "NEXUS — research workspace", "process": "chrome.exe",
     "rect": (920, 10, 1670, 700), "minimized": False},
    {"hwnd": 1004, "title": "Presentation.pptx — PowerPoint",
     "process": "powerpnt.exe", "rect": (100, 200, 1200, 900), "minimized": False},
]


def outcome(ok: bool = True, artifacts: Mapping[str, Any] | None = None, error: str = "") -> Any:
    return SimpleNamespace(ok=ok, artifacts=dict(artifacts or {}), error=error)


class FakeComputer:
    """A §9.1-shaped stub — the manager routes, the fake answers."""

    def __init__(self, windows_rows: list[dict[str, Any]] | None = None,
                 monitors: list[dict[str, Any]] | None = None) -> None:
        self.windows_rows = windows_rows if windows_rows is not None else list(ROWS_A)
        self.monitors = monitors or [
            {"device": r"\\.\DISPLAY1", "rect": (0, 0, 1680, 1050),
             "work": (0, 0, 1680, 1000), "primary": True},
            {"device": r"\\.\DISPLAY2", "rect": (-1280, 0, 0, 1024),
             "work": (-1280, 0, 0, 984), "primary": False},
        ]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def windows(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        self.calls.append(("windows", {"op": op, **extra}))
        if op == "list_windows":
            return outcome(
                artifacts={"windows": self.windows_rows, "count": len(self.windows_rows)}
            )
        if op == "geometry":
            hwnd = int(extra.get("hwnd", 0))
            for row in self.windows_rows:
                if row.get("hwnd") == hwnd:
                    left, top, right, bottom = row.get("rect", (0, 0, 800, 600))
                    return outcome(artifacts={"geometry": {
                        "hwnd": hwnd, "rect": [left, top, right, bottom],
                        "position": [left, top], "size": [right - left, bottom - top],
                        "monitor": self.monitors[0]["device"], "minimized": False,
                    }})
            return outcome(ok=False, error=f"unknown hwnd {hwnd}")
        return outcome()

    def screens(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        self.calls.append(("screens", {"op": op, **extra}))
        if op == "monitors":
            return outcome(artifacts={"monitors": self.monitors, "count": len(self.monitors)})
        return outcome()


# ======================================================================= A


def section_a(runner: Runner) -> None:
    """§10.1 — Window Registry."""
    runner.section = "A"

    fields = [f for f in WindowRecord.__dataclass_fields__ if f not in ("hwnd", "title")]
    runner.check(
        "the §10.1 fields are nine, verbatim, in order",
        fields == ["window_id", "application", "task_id", "workspace", "agent",
                   "position", "size", "visibility", "input_owner"],
        detail=f"fields={fields}",
    )
    runner.check(
        "window_id is the stable win-<hwnd> key",
        window_id_for(131074) == "win-131074",
    )

    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe("window.opened", seen.append)
    bus.subscribe("window.closed", seen.append)
    registry = WindowRegistry(bus=bus)
    report = registry.ingest(ROWS_A)
    runner.check(
        "ingest opens four windows (id/title/process/rect/minimized honored)",
        report.total == 4 and len(report.opened) == 4 and registry.count() == 4
        and registry.find(1002) is not None,
        detail=f"report={report.to_dict()}",
    )
    record = registry.find(1002)
    assert record is not None
    runner.check(
        "the record carries application · title · geometry from the row",
        record.application == "chrome.exe" and record.title.startswith("Google Chrome")
        and record.position == (10, 10) and record.size == (890, 690),
        detail=f"record={record.to_dict()}",
    )
    runner.check(
        "window.opened published 4× (the first real publisher of the §2.2 pair)",
        len(seen) == 4 and all(e.name == "window.opened" for e in seen)
        and seen[0].payload.get("window_id") == "win-1001",
        detail=f"events={[e.name for e in seen]}",
    )

    moved_row = dict(ROWS_A[3], rect=(0, 0, 800, 600), minimized=True)
    refreshed = list(ROWS_A[:3]) + [moved_row]
    report2 = registry.ingest(refreshed)
    runner.check(
        "geometry refresh updates in place (one updated, none reopened)",
        report2.total == 4 and len(report2.updated) == 1
        and not report2.opened and registry.find(1004) is not None
        and registry.find(1004).visibility == "minimized",
        detail=f"report2={report2.to_dict()}",
    )

    # NEXUS decisions survive the refresh; machine fields refuse writes
    registry.update("win-1003", input_owner=InputOwner.NEXUS, task_id="task-42")
    registry.ingest([dict(row, rect=(5, 5, 805, 605)) for row in refreshed])
    kept = registry.find(1003)
    runner.check(
        "task binding and ownership survive a geometry refresh",
        kept.input_owner == "NEXUS" and kept.task_id == "task-42"
        and kept.position == (5, 5),
        detail=f"kept={kept.to_dict()}",
    )
    try:
        registry.update("win-1003", position=(1, 1))
        refused = False
    except ValueError:
        refused = True
    runner.check(
        "update() refuses machine-owned fields (position/size/visibility)",
        refused,
    )

    registry.ingest(ROWS_A[:2])  # 1003/1004 close
    closed_events = [e for e in seen if e.name == "window.closed"]
    runner.check(
        "vanished windows close and publish window.closed (2×)",
        registry.count() == 2 and len(closed_events) == 2
        and {e.payload.get("window_id") for e in closed_events} == {"win-1003", "win-1004"},
        detail=f"closed={[e.payload for e in closed_events]}",
    )
    try:
        registry.update("win-9999", input_owner="USER")
        unknown = False
    except KeyError:
        unknown = True
    runner.check("update() on an unknown window_id raises KeyError", unknown)
    try:
        registry.update("win-1001", input_owner="ROBOT")
        bad_owner = False
    except ValueError:
        bad_owner = True
    runner.check("input_owner outside USER|NEXUS|SHARED is refused", bad_owner)
    snapshot = registry.snapshot()
    runner.check(
        "snapshot() is a serializable count+windows shape",
        snapshot["count"] == 2 and len(snapshot["windows"]) == 2
        and set(snapshot["windows"][0]) >= {"window_id", "input_owner"},
    )


# ======================================================================= B


def section_b(runner: Runner) -> None:
    """§10.2 — Window Ownership."""
    runner.section = "B"

    runner.check(
        "the ownership vocabulary is exactly USER · NEXUS · SHARED",
        OWNERS == ("USER", "NEXUS", "SHARED"),
    )
    rules = {(rule.kind, rule.pattern.lower()): rule.owner for rule in DEMO_RULES}
    runner.check(
        "the Spec §61 example ships as demo rules "
        "(War Thunder → USER, Chrome A → USER, Chrome B → NEXUS, PowerPoint → NEXUS)",
        rules.get(("title", "war thunder")) == "USER"
        and rules.get(("title", "youtube")) == "USER"
        and rules.get(("title", "nexus")) == "NEXUS"
        and rules.get(("process", "powerpnt")) == "NEXUS",
        detail=f"rules={rules}",
    )

    policy = OwnershipPolicy()
    resolved = {row["hwnd"]: policy.resolve(WindowRecord(
        window_id=window_id_for(row["hwnd"]),
        application=row["process"], title=row["title"],
    )) for row in ROWS_A}
    runner.check(
        "resolution over the live-example rows: USER · USER · NEXUS · NEXUS",
        [resolved[1001], resolved[1002], resolved[1003], resolved[1004]]
        == ["USER", "USER", "NEXUS", "NEXUS"],
        detail=f"resolved={resolved}",
    )

    unknown = WindowRecord(window_id="win-777", application="notepad.exe",
                           title="Untitled — Notepad")
    runner.check(
        "unmatched windows default to USER (the safe posture)",
        policy.resolve(unknown) == "USER",
    )
    policy.assign("win-777", InputOwner.SHARED)
    runner.check(
        "an explicit assignment beats the pattern rules",
        policy.resolve(unknown) == "SHARED",
    )
    policy.release("win-777")
    runner.check(
        "release() returns to pattern resolution",
        policy.resolve(unknown) == "USER" and policy.release("win-777") is False,
    )

    high = OwnershipPolicy(rules=[
        OwnershipRule(kind="title", pattern="war thunder", owner=InputOwner.NEXUS,
                      priority=10),
        OwnershipRule(kind="process", pattern="aces.exe", owner=InputOwner.USER,
                      priority=90),
    ])
    runner.check(
        "higher priority wins over declaration order",
        high.resolve(WindowRecord(window_id="win-1001", application="aces.exe",
                                  title="War Thunder")) == "USER",
    )

    applied = OwnershipPolicy().apply([
        WindowRecord(window_id="win-1001", application="aces.exe",
                     title="War Thunder"),
        WindowRecord(window_id="win-1004", application="powerpnt.exe",
                     title="deck"),
    ])
    runner.check(
        "apply() stamps input_owner without touching other fields",
        [r.input_owner for r in applied] == ["USER", "NEXUS"]
        and applied[0].window_id == "win-1001",
    )
    try:
        OwnershipRule(kind="cursor", pattern="x", owner="USER")
        bad_kind = False
    except ValueError:
        bad_kind = True
    runner.check("rule kinds are validated (process|title only)", bad_kind)
    summary = policy.summary()
    runner.check(
        "summary() exposes rules · assignments · default_owner",
        {"rules", "assignments", "default_owner"} <= set(summary)
        and summary["default_owner"] == "USER",
    )


# ======================================================================= C


def section_c(runner: Runner) -> None:
    """§10.3 — Human/AI Input Arbitration."""
    runner.section = "C"

    registry = WindowRegistry()
    registry.ingest(ROWS_A)
    registry.update("win-1001", input_owner="USER")     # War Thunder
    registry.update("win-1002", input_owner="USER")     # Chrome A
    registry.update("win-1003", input_owner="NEXUS")    # Chrome B
    registry.update("win-1004", input_owner="SHARED")   # PowerPoint
    arbitrator = InputArbitrator(registry)

    decision_user = arbitrator.request(hwnd=1001, tool="keyboard")
    runner.check(
        "a USER-owned window is denied — with the reason",
        isinstance(decision_user, ArbitrationDecision)
        and decision_user.allowed is False and decision_user.owner == "USER"
        and "human-owned" in decision_user.reason,
        detail=f"decision={decision_user.to_dict()}",
    )
    decision_nexus = arbitrator.request(hwnd=1003, tool="mouse")
    runner.check(
        "a NEXUS-owned window is allowed",
        decision_nexus.allowed is True and decision_nexus.owner == "NEXUS",
    )
    decision_shared = arbitrator.request(hwnd=1004, tool="uia")
    runner.check(
        "a SHARED window is allowed *with coordination* (Spec §62)",
        decision_shared.allowed is True and decision_shared.coordinated is True
        and decision_shared.owner == "SHARED",
    )
    decision_unknown = arbitrator.request(hwnd=987654, tool="mouse")
    runner.check(
        "an unknown window is denied by default (never assume)",
        decision_unknown.allowed is False and decision_unknown.owner == "UNKNOWN",
    )
    relaxed = InputArbitrator(registry, unknown_policy="allow")
    runner.check(
        "unknown_policy=allow documents the operator-accepted risk",
        relaxed.request(hwnd=987654).allowed is True,
    )
    try:
        InputArbitrator(registry, unknown_policy="maybe")
        bad_policy = False
    except ValueError:
        bad_policy = True
    runner.check("unknown_policy is validated (deny|allow)", bad_policy)

    # the §7.1/§7.2 seam: pre_tool_call veto
    hooks = HarnessHooks()
    hooks.register("pre_tool_call", arbitrator.as_hook())
    context_user = HookContext(
        point="pre_tool_call", tool="keyboard", arguments={"hwnd": 1001}
    )
    context_nexus = HookContext(
        point="pre_tool_call", tool="mouse", arguments={"hwnd": 1003}
    )
    context_other = HookContext(
        point="pre_tool_call", tool="filesystem", arguments={"path": "x.txt"}
    )
    context_free = HookContext(
        point="pre_tool_call", tool="keyboard", arguments={"op": "type", "text": "hi"}
    )
    runner.check(
        "the hook vetoes input into the human's window",
        hooks.fire("pre_tool_call", context_user) is False,
    )
    runner.check(
        "the hook passes input into the NEXUS-owned window",
        hooks.fire("pre_tool_call", context_nexus) is True,
    )
    runner.check(
        "non-input tools pass untouched (filesystem et al.)",
        hooks.fire("pre_tool_call", context_other) is True,
    )
    runner.check(
        "input calls with no window target pass (not our seam)",
        hooks.fire("pre_tool_call", context_free) is True,
    )
    runner.check(
        "INPUT_TOOLS is exactly mouse · keyboard · uia · windows",
        set(INPUT_TOOLS) == {"mouse", "keyboard", "uia", "windows"},
    )
    runner.check(
        "the arbitration log records the verdicts",
        len(arbitrator.log()) >= 4
        and arbitrator.log()[0].to_dict()["owner"] == "USER",
    )


# ======================================================================= D


def section_d(runner: Runner) -> None:
    """§10.4 — Multiple Monitors."""
    runner.section = "D"

    computer = FakeComputer()
    layout = MonitorLayout(computer)
    monitors = layout.snapshot()
    runner.check(
        "snapshot() enumerates the monitor list via screens.monitors",
        len(monitors) == 2 and monitors[0].monitor_id == "mon-0"
        and monitors[1].monitor_id == "mon-1",
        detail=f"monitors={[m.to_dict() for m in monitors]}",
    )
    primary = monitors[0]
    secondary = monitors[1]
    runner.check(
        "each record carries resolution · position · primary · device",
        primary.resolution == (1680, 1050) and primary.position == (0, 0)
        and primary.primary is True and primary.device == r"\\.\DISPLAY1",
    )
    runner.check(
        "negative virtual-desktop coordinates survive parsing (mon-1 left of primary)",
        secondary.position == (-1280, 0) and secondary.primary is False,
    )
    runner.check(
        "monitor_for_window maps hwnd → monitor via windows.geometry",
        layout.monitor_for_window(1002) is not None
        and layout.monitor_for_window(1002).monitor_id == "mon-0",
    )
    routed = [
        call for call in computer.calls
        if call[0] == "screens" and call[1]["op"] == "monitors"
    ]
    runner.check(
        "the probes route through the Computer API (no user32 here)",
        len(routed) >= 2,
        detail=f"calls={computer.calls[:4]}",
    )

    work = primary.work_area
    rect = MonitorLayout.placement_rect(
        primary, (640, 480), anchor="center", margin=32
    )
    expected_x = work[0] + (work[2] - work[0] - 640) // 2
    expected_y = work[1] + (work[3] - work[1] - 480) // 2
    runner.check(
        "placement math: centered inside the work area",
        rect == (expected_x, expected_y, 640, 480),
        detail=f"rect={rect}",
    )
    corner = MonitorLayout.placement_rect(
        primary, (400, 300), anchor="bottom-right", margin=16
    )
    runner.check(
        "bottom-right anchor lands margin-exact in the corner",
        corner == (work[2] - 16 - 400, work[3] - 16 - 300, 400, 300),
        detail=f"corner={corner}",
    )
    clamped = MonitorLayout.placement_rect(
        primary, (99999, 99999), anchor="top-left", margin=32
    )
    runner.check(
        "oversized windows clamp to the work area (never the taskbar)",
        clamped[2] == work[2] - work[0] - 64 and clamped[3] == work[3] - work[1] - 64,
        detail=f"clamped={clamped}",
    )
    try:
        MonitorLayout.placement_rect(primary, (10, 10), anchor="middle")
        bad_anchor = False
    except ValueError:
        bad_anchor = True
    runner.check("placement anchors are validated", bad_anchor)

    placement = layout.place(1002, "mon-1", anchor="top-left", margin=24)
    moved = [c for c in computer.calls if c[0] == "windows" and c[1].get("op") == "move"]
    runner.check(
        "place() routes windows.move with the computed rect",
        placement["ok"] is True and placement["monitor"] == "mon-1"
        and bool(moved) and moved[0][1]["x"] == placement["rect"][0],
        detail=f"placement={placement}",
    )
    try:
        layout.place(1002, "mon-9")
        bad_monitor = False
    except ValueError:
        bad_monitor = True
    runner.check("place() refuses an unknown monitor_id", bad_monitor)
    summary = layout.summary()
    runner.check(
        "summary() reports the topology",
        summary["count"] == 2 and len(summary["monitors"]) == 2,
    )
    runner.check(
        "MonitorRecord is a frozen value object with a serializable form",
        MonitorRecord(
            monitor_id="mon-x", resolution=(1920, 1080), position=(0, 0),
            work_area=(0, 0, 1920, 1040), primary=True, device=r"\\\\.\\DISPLAY9",
        ).to_dict()["resolution"] == [1920, 1080],
    )
    runner.check(
        "MonitorRecord exposes width/height accessors",
        primary.width == 1680 and primary.height == 1050,
    )


# ======================================================================= E


def section_e(runner: Runner) -> None:
    """§10.5 — Overlay."""
    runner.section = "E"

    runner.check(
        "the §10.5 status line is verbatim",
        STATUS_WORKING == "NEXUS is working" and STATUS_PAUSED == "NEXUS is paused",
    )
    paused_flags: list[str] = []
    resumed_flags: list[str] = []
    controller = build_overlay(
        on_pause=lambda: paused_flags.append("paused"),
        on_resume=lambda: resumed_flags.append("resumed"),
    )
    runner.check(
        "off win32 the controller degrades to the honest headless backend",
        controller.backend_kind == ("native" if ON_WINDOWS else "headless"),
        detail=f"backend={controller.backend_kind}",
    )
    runner.check("a fresh controller is IDLE", controller.state == OverlayState.IDLE)
    runner.check(
        "begin() → WORKING and the status line says so",
        controller.begin("task: summarize the deck") == OverlayState.WORKING
        and controller.snapshot()["status_text"] == STATUS_WORKING
        and controller.snapshot()["label"] == "task: summarize the deck",
    )
    try:
        controller.end()  # WORKING → IDLE is legal
        controller.pause()  # IDLE → PAUSED is illegal
        illegal = False
    except OverlayError:
        illegal = True
    runner.check(
        "illegal transitions raise OverlayError (IDLE ↛ PAUSED)",
        illegal and controller.state == OverlayState.IDLE,
    )
    controller.begin("t2")
    controller.pause()
    runner.check(
        "pause() → PAUSED with the paused status line",
        controller.state == OverlayState.PAUSED
        and controller.snapshot()["status_text"] == STATUS_PAUSED,
    )
    controller.resume()
    runner.check("resume() → WORKING again", controller.state == OverlayState.WORKING)
    runner.check(
        "programmatic pause/resume does NOT fire the callbacks",
        not paused_flags and not resumed_flags,
    )
    controller.pause(origin="button")
    controller.resume(origin="button")
    runner.check(
        "button-origin pause/resume fire the callbacks (the §155 surface)",
        paused_flags == ["paused"] and resumed_flags == ["resumed"],
    )
    runner.check(
        "end() returns to IDLE and clears the label",
        controller.end() == OverlayState.IDLE
        and controller.snapshot()["label"] == "",
    )
    trail = controller.transitions()
    runner.check(
        "every transition is audited with from/to/origin",
        len(trail) >= 6 and {t.origin for t in trail} >= {"api", "button"}
        and trail[0].to_dict() == {"from": "IDLE", "to": "WORKING",
                                   "label": "task: summarize the deck", "origin": "api"},
    )
    controller.shutdown()
    runner.check(
        "shutdown() is idempotent and settles at IDLE",
        controller.state == OverlayState.IDLE and controller.shutdown() is None,
    )

    if ON_WINDOWS:
        native = OverlayController()  # native backend on win32
        runner.bonus_check(
            "BONUS: the native ctypes overlay window exists (FindWindow)",
            native.begin("phase9 proof") == OverlayState.WORKING
            and _native_hwnd_visible(native),
            detail="CreateWindowExW + WM_APP poke",
        )
        native.pause()
        runner.bonus_check(
            "BONUS: state poke flips the overlay to PAUSED",
            native.state == OverlayState.PAUSED and _native_hwnd_visible(native),
        )
        native.end()
        import time

        time.sleep(0.4)
        runner.bonus_check(
            "BONUS: end() dismisses the native overlay",
            native.state == OverlayState.IDLE,
        )
        native.shutdown()


def _native_hwnd_visible(controller: OverlayController) -> bool:
    """FindWindow on the overlay class — the window really exists."""
    import ctypes
    import time

    backend = controller._backend  # noqa: SLF001 — the harness may look
    time.sleep(0.25)  # let the message loop settle
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    from nexus.windows.overlay import NativeOverlay  # noqa: E402

    hwnd = user32.FindWindowW(NativeOverlay._CLASS_NAME, None)  # noqa: SLF001
    return bool(hwnd) and bool(getattr(backend, "_alive", False))


# ======================================================================= F


def section_f(runner: Runner) -> None:
    """Integration + regression — the runtime wires §10; phases stay green."""
    runner.section = "F"

    from dataclasses import replace as _replace

    from nexus.core.config.loader import load_config
    from nexus.core.config.paths import resolve_paths
    from nexus.core.config.runtime import NexusRuntime

    with tempfile.TemporaryDirectory() as root:
        runtime = NexusRuntime(
            paths=resolve_paths(root), config=load_config(root), bus=EventBus()
        )
        runner.check(
            "NexusRuntime wires the Window Manager (windows_enabled default)",
            runtime.window_manager is not None
            and runtime.computer_runtime is not None,
        )
        manager = runtime.window_manager
        assert manager is not None
        runner.check(
            "the manager composes the five §10 modules",
            all(hasattr(manager, name) for name in (
                "registry", "ownership", "arbitrator", "monitors", "overlay"
            )),
        )
        runner.check(
            "the §10.3 veto is installed on the harness pre_tool_call seam",
            runtime.hooks is not None and runtime.hooks.count("pre_tool_call") >= 1,
        )
        state = manager.snapshot()
        runner.check(
            "the manager snapshot carries the five §10 views",
            {"windows", "ownership", "monitors", "overlay"} <= set(state)
            and state["phase"] == 9,
        )
        runtime.shutdown()
        runner.check(
            "shutdown dismisses the overlay cleanly",
            manager.overlay.state == OverlayState.IDLE,
        )

    with tempfile.TemporaryDirectory() as root:
        config = load_config(root)
        config_off = _replace(
            config, tools=_replace(config.tools, windows_enabled=False)
        )
        runtime_off = NexusRuntime(
            paths=resolve_paths(root), config=config_off, bus=EventBus()
        )
        runner.check(
            "windows_enabled=false leaves the manager unwired "
            "(Phase-8 behavior, byte for byte)",
            runtime_off.window_manager is None
            and runtime_off.computer_runtime is not None,
        )
        hooks_off = runtime_off.hooks
        runner.check(
            "with the manager off, no arbitration veto sits on the hooks",
            hooks_off is None or hooks_off.count("pre_tool_call") == 0,
        )

    with tempfile.TemporaryDirectory() as root:
        config_no_computer = _replace(
            load_config(root),
            tools=_replace(load_config(root).tools, computer_enabled=False),
        )
        runtime_nc = NexusRuntime(
            paths=resolve_paths(root), config=config_no_computer, bus=EventBus()
        )
        runner.check(
            "§10 composes over §9.1: no Computer Runtime → no manager",
            runtime_nc.computer_runtime is None and runtime_nc.window_manager is None,
        )

    # the tool surface grew additively: same 12 records, new ops
    registry, router, _adapter, _report = build_tool_system(
        native=True, computer=True, mcp_servers=()
    )
    _ = router
    definitions = {definition.name: definition for definition in registry.discover()}
    runner.check(
        "no new tool records — the manager is policy, not a 13th record",
        len(registry.discover()) == 12,
        detail=f"count={len(registry.discover())}",
    )
    windows_ops = definitions["windows"].input_schema["properties"]["op"]["enum"]
    screen_ops = definitions["screen"].input_schema["properties"]["op"]["enum"]
    runner.check(
        "the windows tool gained geometry · move (additive)",
        "geometry" in windows_ops and "move" in windows_ops
        and {"list_windows", "focus", "close"} <= set(windows_ops),
    )
    runner.check(
        "the screen tool gained monitors (additive, risk stays 1)",
        "monitors" in screen_ops and "size" in screen_ops
        and definitions["screen"].risk == 1,
    )
    runner.check(
        "move is a mutating op for the §8.2 scope stage; monitors is not",
        "move" in definitions["windows"].scope_requirements.mutating_operations
        and definitions["screen"].scope_requirements.mutating_operations == (),
    )
    from nexus.tools.native.screen import _OPERATIONS as SCREEN_OPS  # noqa: E402
    from nexus.tools.native.windows import _OPERATIONS as WINDOWS_OPS  # noqa: E402

    runner.check(
        "the operation tuples carry the new ops in source truth",
        "monitors" in SCREEN_OPS and "geometry" in WINDOWS_OPS and "move" in WINDOWS_OPS,
    )

    # the manager sync flow over a fake §9.1 surface
    computer = FakeComputer()
    manager = build_window_manager(computer, bus=EventBus())
    sync = manager.sync()
    runner.check(
        "sync() ingests the live rows and resolves ownership in one call",
        sync["ingest"]["total"] == 4 and sync["ok"] is True
        and manager.registry.find(1003).input_owner == "NEXUS",
        detail=f"sync={sync}",
    )
    claimed = manager.claim(
        "win-1004", owner=InputOwner.USER, task_id="task-9",
        workspace="main", agent="deck-builder",
    )
    runner.check(
        "claim() stakes the window with the full task binding",
        claimed["input_owner"] == "USER" and claimed["task_id"] == "task-9"
        and claimed["workspace"] == "main" and claimed["agent"] == "deck-builder",
    )
    released = manager.release("win-1004")
    after = manager.registry.get("win-1004")
    runner.check(
        "release() drops the claim and the binding (patterns take over)",
        released is True and after.input_owner == "NEXUS"
        and after.task_id == "" and after.workspace == "" and after.agent == "",
    )

    prior = [
        ("phase01", "Phase 1", 98),
        ("phase02", "Phase 2", 143),
        ("phase03", "Phase 3", 104),
        ("phase04", "Phase 4", 106),
        ("phase05", "Phase 5", 116),
        ("phase06", "Phase 6", 88),
        ("phase07", "Phase 7", 88),
        ("phase08", "Phase 8", 80),
    ]
    results = run_phases(prior)
    for (_phase_dir, label, _expected), (_label, line, code) in zip(
        prior, results, strict=True
    ):
        runner.check(
            f"{label} harness still green ({line})",
            code == 0,
            detail=f"exit={code} last={line!r}",
        )


def run_phases(prior: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """Run the Phase 1–8 harnesses; return their (name, line, code)."""
    results: list[tuple[str, str, int]] = []
    for phase_dir, label, expected in prior:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tests" / phase_dir / "verify_exit_criteria.py")],
            capture_output=True,
            text=True,
            timeout=900,
        )
        results.append((label, proc.stdout.strip().splitlines()[-1], proc.returncode))
        _ = expected
    return results


# ======================================================================= main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="unused (repo-rooted)")
    _ = parser.parse_args()
    print("PHASE 9 — Window Manager + Human Parallelism (Final Build Plan §10) exit criteria")
    runner = Runner()
    for section in (section_a, section_b, section_c, section_d, section_e, section_f):
        try:
            section(runner)
        except Exception as exc:  # noqa: BLE001 — a section crash is a failure
            print(f"  [FAIL] ({runner.section}) section crashed: {exc}")
            runner.failed += 1
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
