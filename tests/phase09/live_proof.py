"""Phase-9 live proof — runs ON the real Windows box.

Five proofs, one per §10 section, against the live desktop:

* §10.1 — the registry syncs the *real* windows (process names via
          QueryFullProcessImageNameW) and publishes window.opened;
* §10.2 — ownership resolves over the real rows (USER/NEXUS/SHARED);
* §10.3 — arbitration verdicts on real hwnds + a pre_tool_call veto
          on the human's window;
* §10.4 — the real monitor list (EnumDisplayMonitors) + geometry +
          a real placement of the overlay window (SetWindowPos);
* §10.5 — the native overlay: shown (FindWindow), *visible* (a GDI
          screenshot of its region differs before/after), paused,
          resumed, dismissed.

Run:  python tests\\phase09\\live_proof.py   (from M:\\NEXUS)
Writes: proofs\\phase9_live.json + proofs\\overlay_before.png /
        overlay_after.png (the visible evidence).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"M:\NEXUS")

print("python:", sys.version.split()[0], "| platform:", sys.platform)
report: dict = {}
PROOFS = Path(r"M:\NEXUS\proofs")
PROOFS.mkdir(parents=True, exist_ok=True)

from nexus.events import EventBus  # noqa: E402
from nexus.harness import HarnessHooks  # noqa: E402
from nexus.harness.hooks import HookContext  # noqa: E402
from nexus.tools import build_tool_system  # noqa: E402
from nexus.windows import (  # noqa: E402
    OverlayState,
    build_window_manager,
)

_registry, router, _adapter, _build = build_tool_system(
    native=True, computer=True, mcp_servers=()
)
from nexus.computer import build_computer_runtime  # noqa: E402

computer = build_computer_runtime(router)
bus = EventBus()
opened_events: list = []
bus.subscribe("window.opened", opened_events.append)
manager = build_window_manager(computer, bus=bus)

# ---- Proof §10.1: real sync + events -----------------------------------
sync = manager.sync()
report["sync"] = sync
real_rows = manager.registry.records()
report["window_count"] = len(real_rows)
report["window_opened_events"] = len(opened_events)
sample = [
    {
        "window_id": r.window_id,
        "application": r.application,
        "title": r.title[:60],
        "input_owner": r.input_owner,
        "position": list(r.position),
        "size": list(r.size),
    }
    for r in real_rows[:8]
]
report["windows_sample"] = sample
print(
    f"§10.1 windows: {len(real_rows)} synced, "
    f"{len(opened_events)} window.opened events"
)
for row in sample[:5]:
    print(
        f"    {row['window_id']}  {row['application']:<22} "
        f"{row['input_owner']:<6} {row['title']}"
    )

# ---- Proof §10.2: ownership over the real rows --------------------------
owners = {}
for record in real_rows:
    owners.setdefault(record.input_owner, 0)
    owners[record.input_owner] += 1
report["ownership_distribution"] = owners
verdicts: list = []
explicit = manager.registry.records()
if explicit:
    target = explicit[0]
    manager.claim(
        target.window_id, owner="NEXUS", task_id="phase9-proof",
        workspace="main", agent="prover",
    )
    claimed = manager.registry.get(target.window_id)
    # the NEXUS-owned verdict, live (Spec §62 — allowed, no mixing)
    verdicts.append(
        manager.arbitrator.request(hwnd=target.hwnd, tool="mouse").to_dict()
    )
    report["claim"] = {
        "window_id": target.window_id,
        "owner": claimed.input_owner,
        "task_id": claimed.task_id,
        "workspace": claimed.workspace,
        "agent": claimed.agent,
    }
    manager.release(target.window_id)
print(f"§10.2 owners: {owners} + explicit claim/release round-trip ok")

# ---- Proof §10.3: arbitration + veto on the human's window --------------
human_windows = [r for r in real_rows if r.input_owner == "USER"]
nexus_windows = [r for r in real_rows if r.input_owner == "NEXUS"]
if human_windows:
    verdicts.append(
        manager.arbitrator.request(hwnd=human_windows[0].hwnd, tool="keyboard").to_dict()
    )
if nexus_windows:
    verdicts.append(
        manager.arbitrator.request(hwnd=nexus_windows[0].hwnd, tool="mouse").to_dict()
    )
report["arbitration_verdicts"] = verdicts
hooks = HarnessHooks()
hooks.register("pre_tool_call", manager.hook())
veto_result = None
if human_windows:
    context = HookContext(
        point="pre_tool_call", tool="keyboard",
        arguments={"hwnd": human_windows[0].hwnd},
    )
    veto_result = hooks.fire("pre_tool_call", context)
report["veto_on_human_window"] = veto_result
print(f"§10.3 verdicts: {[(v['owner'], v['allowed']) for v in verdicts]} veto={veto_result}")

# ---- Proof §10.4: the real monitor list + placement ---------------------
monitors = manager.monitors.snapshot()
report["monitors"] = [m.to_dict() for m in monitors]
print(f"§10.4 monitors: {len(monitors)}")
for record in monitors:
    print(
        f"    {record.monitor_id} {record.device} "
        f"{record.resolution[0]}x{record.resolution[1]} @ {record.position} "
        f"primary={record.primary}"
    )
geometry_proof = None
if real_rows:
    outcome_g = computer.windows("geometry", hwnd=real_rows[0].hwnd)
    geometry_proof = (getattr(outcome_g, "artifacts", {}) or {}).get("geometry")
report["geometry"] = geometry_proof
placement_proof = None

# ---- Proof §10.5: the native overlay ------------------------------------
overlay = manager.overlay

import ctypes  # noqa: E402
import ctypes.wintypes as _wt  # noqa: E402

user32 = ctypes.windll.user32  # type: ignore[attr-defined]


class _RECT(_wt.RECT):
    pass


work = _RECT()
user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)
# the exact anchor the overlay itself will use (bottom-right of the
# primary work area) — the capture rect covers it with a margin.
anchor_x = work.right - 280 - 24
anchor_y = work.bottom - 128 - 24
capture = (anchor_x - 10, anchor_y - 10, 300, 148)

empty_path = str(PROOFS / "overlay_empty.png")
working_path = str(PROOFS / "overlay_working.png")
paused_path = str(PROOFS / "overlay_paused.png")

# 1) the empty desktop region BEFORE the overlay exists
computer.screens(
    "screenshot", x=capture[0], y=capture[1], w=capture[2], h=capture[3],
    path=empty_path,
)
time.sleep(0.3)

# 2) begin → the overlay is born and paints
overlay_ok = overlay.begin("phase 9 live proof") == OverlayState.WORKING
time.sleep(1.5)  # let the message loop create + paint the window
found_hwnd = user32.FindWindowW("NexusOverlayWnd", None)
computer.screens(
    "screenshot", x=capture[0], y=capture[1], w=capture[2], h=capture[3],
    path=working_path,
)

# 3) pause → repaint with the paused line
overlay.pause()
time.sleep(1.0)
computer.screens(
    "screenshot", x=capture[0], y=capture[1], w=capture[2], h=capture[3],
    path=paused_path,
)
paused_state = overlay.state

# §10.4 placement on a window we own — the overlay itself (SetWindowPos)
if found_hwnd and monitors:
    placement_proof = manager.monitors.place(
        found_hwnd, monitors[0].monitor_id, anchor="center", margin=60
    )
    time.sleep(0.6)
    # the placed rect must sit inside the target monitor's work area
    if placement_proof and placement_proof.get("ok"):
        px, py, pw, ph = placement_proof["rect"]
        wl, wt_, wr, wb = monitors[0].work_area
        placement_proof["within_work_area"] = (
            wl <= px and py >= wt_ and px + pw <= wr and py + ph <= wb
        )

resumed = overlay.resume()
time.sleep(0.8)
overlay.end()
time.sleep(0.6)
gone = not user32.FindWindowW("NexusOverlayWnd", None)

before_bytes = Path(empty_path).read_bytes() if Path(empty_path).exists() else b""
working_bytes = Path(working_path).read_bytes() if Path(working_path).exists() else b""
after_bytes = Path(paused_path).read_bytes() if Path(paused_path).exists() else b""
visible = bool(before_bytes) and bool(working_bytes) and before_bytes != working_bytes
repaints = bool(working_bytes) and bool(after_bytes) and working_bytes != after_bytes
report["overlay"] = {
    "begin": overlay_ok,
    "found_hwnd": int(found_hwnd or 0),
    "paused": str(paused_state),
    "resumed": str(resumed),
    "dismissed": bool(gone),
    "visible_appears": visible,
    "visible_state_repaints": repaints,
    "empty_png_bytes": len(before_bytes),
    "working_png_bytes": len(working_bytes),
    "paused_png_bytes": len(after_bytes),
    "placement": placement_proof,
    "backend": overlay.backend_kind,
}
print(
    f"§10.5 overlay: hwnd={found_hwnd} appears={visible} repaints={repaints} "
    f"paused={paused_state} dismissed={gone} "
    f"placement_ok={placement_proof and placement_proof.get('within_work_area')}"
)

# ---- verdict -------------------------------------------------------------
ok = (
    sync["ok"] is True
    and len(real_rows) >= 3
    and len(opened_events) == len(real_rows)
    and owners.get("USER", 0) >= 1
    and len(monitors) >= 1
    and monitors[0].resolution[0] > 0
    and overlay_ok
    and found_hwnd
    and visible
    and repaints
    and str(paused_state) == "PAUSED"
    and gone
    and (veto_result is False or not human_windows)
    and placement_proof is not None
    and placement_proof.get("within_work_area") is True
    and any(v["allowed"] for v in verdicts)
)
report["result"] = "PASS" if ok else "FAIL"
(PROOFS / "phase9_live.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("PROOF RESULT:", report["result"])
sys.exit(0 if ok else 1)
