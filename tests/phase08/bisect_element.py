"""Bisect the element property calls on the device."""

import ctypes
import sys

sys.path.insert(0, r"M:\NEXUS")
from nexus.computer import uia_native

print("1: automation...", flush=True)
automation = uia_native._automation()
print("   ptr:", hex(automation), flush=True)

print("2: GetFocusedElement via _call...", flush=True)
pointer = ctypes.c_void_p()
uia_native._call(
    automation, 8, "GetFocusedElement",
    (ctypes.POINTER(ctypes.c_void_p),), (ctypes.byref(pointer),),
)
print("   out:", hex(pointer.value or 0), flush=True)

element = uia_native.UIAElement(int(pointer.value))
print("3: element wrapped", flush=True)

print("4: process_id (slot 18)...", flush=True)
print("   ->", element.process_id, flush=True)

print("5: control_type (slot 19)...", flush=True)
print("   ->", element.control_type, flush=True)

print("6: name (slot 21)...", flush=True)
print("   ->", repr(element.name), flush=True)

print("7: is_enabled (slot 26)...", flush=True)
print("   ->", element.is_enabled, flush=True)

print("8: class_name (slot 28)...", flush=True)
print("   ->", repr(element.class_name), flush=True)

print("9: rectangle (slot 10 + VARIANT)...", flush=True)
print("   ->", element.rectangle, flush=True)

print("10: release...", flush=True)
element.release()
print("    released OK", flush=True)
print("DONE", flush=True)
