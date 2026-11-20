"""Phase-10 live proof — runs ON the real Windows box (via the t1 bridge).

Proves the §11 surface against the operator's real machine:

* §11.1 — the agent session launches on the **system Chrome**
  (channel ladder: chromium → chrome) with its own isolated profile;
  real navigation · DOM · forms · tabs · screenshot;
* §11.4 — a *second* Chrome (stand-in user browser, CDP-enabled
  temp profile) attaches via ``connect_over_cdp`` — the §55 gate
  with explicit consent + URL; two sessions live side by side,
  profiles never mixed;
* §11.5 — the DPAPI vault round-trip (store from file → issue →
  redact) **and** the never-crossing secret: a form typed via
  ``vault_ref`` — the secret string must appear in ZERO tool
  outputs and ZERO bus events;
* §10 — ``claim_new_windows`` stakes the agent's Chrome windows as
  NEXUS (the §10.3 arbitration then guards the human's browser
  while the agent works in its own).

Run:  python tests\\phase10\\live_proof_device.py   (from M:\\NEXUS)
Writes: proofs\\phase10_live.json + proofs\\phase10_browser.png
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"M:\NEXUS")

print("python:", sys.version.split()[0], "| platform:", sys.platform)
PROOFS = Path(r"M:\NEXUS\proofs")
PROOFS.mkdir(parents=True, exist_ok=True)
report: dict = {}

from nexus.browser import set_engine_defaults  # noqa: E402
from nexus.events import EventBus  # noqa: E402
from nexus.tools import build_tool_system  # noqa: E402

WORK = PROOFS / "phase10-work"
WORK.mkdir(parents=True, exist_ok=True)

set_engine_defaults(
    channel="chromium", headless=False, data_root=WORK / "nexus-data",
    user_consent=True,  # the operator's explicit §55 opt-in for this proof
)
bus = EventBus()
_registry, router, _adapter, _build = build_tool_system(
    native=True, computer=True, browser=True, mcp_servers=(), bus=bus
)

def call(op: str, **arguments: object):
    outcome = router.route("browser", {"op": op, **arguments}, task_id="phase10-live")
    print(f"  {op:<12} ok={outcome.ok} {str(outcome.output)[:70]}")
    return outcome

# ---- §11.1: the agent session on the system Chrome -----------------------
nav = call("navigate", url="https://example.org")
report["navigate"] = {"ok": bool(nav.ok), "url": str(nav.output)[:120]}

dom = call("read", selector="css=h1")
report["dom_read"] = {
    "ok": bool(dom.ok),
    "text": str(dom.artifacts.get("text", ""))[:80],
}

form_page = WORK / "form.html"
form_page.write_text(
    "<html><head><title>NEXUS Login Proof</title></head><body>"
    "<input id=user type=text><input id=pw type=password>"
    "<h1 id=t>form</h1></body></html>",
    encoding="utf-8",
)
call("navigate", url=form_page.as_uri())
call("fill", selector="css=#user", text="nexus-agent")

# ---- §11.5: the vault (DPAPI, win32) + the never-crossing secret ---------
secret_file = WORK / "secret.txt"
SECRET = "ph10-SECRET-7f3a9"
secret_file.write_text(SECRET, encoding="utf-8")
store = call("vault_store", site="proof.example", username="nexus-agent",
             secret_path=str(secret_file))
report["vault_store"] = {"ok": bool(store.ok), "stored": str(store.artifacts.get("stored", ""))[:120]}

listing = call("vault_list")
entries = listing.artifacts.get("entries", [])
report["vault_list"] = {"ok": bool(listing.ok), "entries": entries}

typed = call("type", selector="css=#pw", vault_ref="proof.example")
report["vault_type"] = {
    "ok": bool(typed.ok),
    "secret_echoed": SECRET in str(typed.output) or SECRET in str(typed.artifacts),
}

# the whole bus history + every output must be secret-free (§11.5)
history_dump = json.dumps(
    [event.to_dict() for event in bus.history_snapshot()], ensure_ascii=False
)
report["secret_in_events"] = SECRET in history_dump
report["event_count"] = len(bus.history_snapshot())

# the vault round-trip (issue + redact) — engine seam only
from nexus.browser.engine import get_engine  # noqa: E402

engine = get_engine()
username, secret_value = engine.vault.issue("proof.example")
report["vault_roundtrip"] = {
    "username": username,
    "ok": secret_value == SECRET,
    "redaction": engine.vault.redact(f"leak {SECRET} now") == "leak [REDACTED] now",
}
_ = engine.vault.redact("")

# ---- §11.1 states/tabs/screenshot ----------------------------------------
tabs = call("tabs")
report["tabs"] = {"ok": bool(tabs.ok), "count": tabs.artifacts.get("count", 0)}
shot = call("screenshot", path=str(PROOFS / "phase10_browser.png"))
report["screenshot"] = {
    "ok": bool(shot.ok),
    "bytes": (PROOFS / "phase10_browser.png").stat().st_size if (PROOFS / "phase10_browser.png").exists() else 0,
}
report["channel"] = engine.active_channel

# ---- §11.4: the user session over CDP (a stand-in user Chrome) -----------
user_profile = WORK / "user-standin-profile"
user_profile.mkdir(parents=True, exist_ok=True)
chrome_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
chrome_exe = next((p for p in chrome_paths if Path(p).exists()), "")
report["cdp_chrome_found"] = bool(chrome_exe)
user_proc = None
if chrome_exe:
    user_proc = subprocess.Popen([
        chrome_exe,
        "--remote-debugging-port=9223",
        f"--user-data-dir={user_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ], creationflags=0x00000008)
    time.sleep(3.0)
    attach = call("attach", cdp_url="http://127.0.0.1:9223", session="user")
    report["cdp_attach"] = {"ok": bool(attach.ok), "pages": str(attach.output)[:80]}
    user_nav = call("snapshot", session="user")
    report["user_session_snapshot"] = {"ok": bool(user_nav.ok)}
    sessions = engine._sessions.snapshot()  # noqa: SLF001 — the proof may look
    report["sessions"] = {
        "count": sessions["count"],
        "kinds": [row["kind"] for row in sessions["sessions"]],
        "profiles_isolated": all(
            "agent-profile" in row.get("profile_dir", "") or row["kind"] == "user"
            for row in sessions["sessions"]
        ),
    }

# ---- §10: the agent windows claimed as NEXUS (a fresh diff) --------------
from nexus.computer import build_computer_runtime  # noqa: E402
from nexus.windows import build_window_manager  # noqa: E402

computer = build_computer_runtime(router)
manager = build_window_manager(computer, bus=bus)
# close the agent context first — the diff must bracket the launch
call("close")
claim = engine.claim_new_windows(manager)
report["claim_new_windows"] = claim
nexus_rows = [
    {"window_id": r.window_id, "application": r.application, "title": r.title[:40]}
    for r in manager.registry.records()
    if r.input_owner == "NEXUS"
]
report["nexus_owned_windows"] = nexus_rows[:6]

# ---- teardown ---------------------------------------------------------------
call("close")
if user_proc is not None:
    user_proc.terminate()
engine.shutdown()

ok = (
    report["navigate"]["ok"]
    and report["dom_read"]["ok"]
    and report["vault_store"]["ok"]
    and report["vault_roundtrip"]["ok"]
    and report["vault_roundtrip"]["redaction"]
    and report["vault_type"]["ok"]
    and not report["vault_type"]["secret_echoed"]
    and not report["secret_in_events"]
    and report["tabs"]["ok"]
    and report["screenshot"]["ok"]
    and report["screenshot"]["bytes"] > 0
    and report.get("cdp_attach", {}).get("ok", False)
    and report.get("sessions", {}).get("count", 0) >= 2
    and report["claim_new_windows"].get("claimed", 0) >= 1
)
report["result"] = "PASS" if ok else "FAIL"
(PROOFS / "phase10_live.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("PROOF RESULT:", report["result"])
sys.exit(0 if ok else 1)
