"""Scan element vtable slots 14..34 with a safe 8-byte read (no
dereference) to map the REAL property-getter layout on this box."""

import ctypes
import sys

sys.path.insert(0, r"M:\NEXUS")
from nexus.computer import uia_native

automation = uia_native._automation()
pointer = ctypes.c_void_p()
uia_native._call(
    automation, 8, "GetFocusedElement",
    (ctypes.POINTER(ctypes.c_void_p),), (ctypes.byref(pointer),),
)
element_ptr = int(pointer.value)
print("element:", hex(element_ptr), flush=True)


def probe(slot):
    buffer = ctypes.c_ulonglong()
    try:
        uia_native._call(
            element_ptr, slot, f"slot{slot}",
            (ctypes.POINTER(ctypes.c_ulonglong),),
            (ctypes.byref(buffer),),
        )
        return buffer.value
    except Exception as exc:
        return f"ERR:{exc}"


for slot in range(14, 35):
    value = probe(slot)
    print(f"slot {slot}: {value}", flush=True)

print("SCAN DONE", flush=True)
