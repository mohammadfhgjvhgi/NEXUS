"""Phase-8 live proof — runs ON the real Windows box.

Proof A: the §9.4 native ctypes UIA client reads the focused element.
Proof C: the §9.5 hierarchy answers live (uia ×2 + input ×1).
Proof D: every §9.1 domain probes honestly on win32.

Run:  python tests\\phase08\\live_proof.py   (from M:\\NEXUS)
"""

import json
import sys

sys.path.insert(0, r"M:\NEXUS")

print("python:", sys.version.split()[0], "| platform:", sys.platform)
report = {}

# ---- Proof A: native UIA focused element (§9.4)
from nexus.computer import uia_native

element = uia_native.focused_element()
try:
    record = element.record()
finally:
    element.release()
report["focused_element"] = record
print("A. focused element:", json.dumps(record, ensure_ascii=False))

# ---- Proof C: hierarchy live (§9.5)
from nexus.computer import ComputerRuntime
from nexus.tools import build_tool_system

_registry, router, _adapter, _build = build_tool_system(
    native=True, computer=True, mcp_servers=()
)
runtime = ComputerRuntime(router)
description = runtime.capability_report()
report["hierarchy"] = description["hierarchy"]
print("C. hierarchy:")
for layer, entry in description["hierarchy"].items():
    print(
        f"   {layer}: providers={entry['providers']} "
        f"available={entry['available']}"
    )

# ---- domains honest on win32
for domain in ("screens", "windows", "mouse", "keyboard", "uia"):
    entry = description[domain]
    print(f"D. {domain}: available={entry['available']} ({entry['reason'][:50]})")

ok = (
    isinstance(record.get("process_id"), int)
    and description["hierarchy"]["uia"]["available"]
    and description["hierarchy"]["input"]["available"]
    and description["mouse"]["available"]
)
print("PROOF RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
