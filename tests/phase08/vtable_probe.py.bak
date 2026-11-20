"""Isolated vtable probe for IUIAutomation on the device."""

import ctypes
import sys


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def guid(text):
    digits = text.strip("{}").replace("-", "")
    g = GUID()
    g.Data1 = int(digits[0:8], 16)
    g.Data2 = int(digits[8:12], 16)
    g.Data3 = int(digits[12:16], 16)
    for i in range(8):
        g.Data4[i] = int(digits[16 + i * 2 : 18 + i * 2], 16)
    return g


print("start", flush=True)
ole32 = ctypes.windll.ole32
print("CoInitializeEx:", hex(ole32.CoInitializeEx(None, 0) & 0xFFFFFFFF), flush=True)

clsid = guid("{ff48dba4-60ef-4201-aa87-54103eef594e}")
iid = guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")
pp = ctypes.c_void_p()
hr = ole32.CoCreateInstance(
    ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(pp)
)
print("CoCreateInstance:", hex(hr & 0xFFFFFFFF), "ptr:", pp.value, flush=True)
if hr != 0 or not pp.value:
    sys.exit(1)

ptr = int(pp.value)
vtable = ctypes.c_void_p.from_address(ptr).value
print("vtable:", hex(vtable or 0), flush=True)

for index in (5, 8):
    address = ctypes.c_void_p.from_address(vtable + 8 * index).value
    print(f"slot {index} fn:", hex(address or 0), flush=True)
    prototype = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
    )(address)
    out = ctypes.c_void_p()
    try:
        result = prototype(ctypes.c_void_p(ptr), ctypes.byref(out))
        print(f"slot {index} hr:", hex(result & 0xFFFFFFFF), "out:", out.value, flush=True)
    except Exception as exc:
        print(f"slot {index} raised:", exc, flush=True)

print("done", flush=True)
