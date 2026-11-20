"""Verify FindAll(6) + GetCurrentPropertyValue(10) with CORRECT args."""

import ctypes
import sys

sys.path.insert(0, r"M:\NEXUS")
from nexus.computer import uia_native

automation = uia_native._automation()
print("automation:", hex(automation), flush=True)

# CreateTrueCondition at automation slot 17
condition = ctypes.c_void_p()
uia_native._call(
    automation, 17, "CreateTrueCondition",
    (ctypes.POINTER(ctypes.c_void_p),), (ctypes.byref(condition),),
)
print("condition:", hex(condition.value or 0), flush=True)

# root element (automation slot 5)
root_ptr = ctypes.c_void_p()
uia_native._call(
    automation, 5, "GetRootElement",
    (ctypes.POINTER(ctypes.c_void_p),), (ctypes.byref(root_ptr),),
)
print("root:", hex(root_ptr.value or 0), flush=True)

# FindAll at ELEMENT slot 6: (scope=CHILDREN, condition, SAFEARRAY**)
array = ctypes.c_void_p()
uia_native._call(
    int(root_ptr.value), 6, "FindAll",
    (ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
    (2, condition, ctypes.byref(array)),
)
print("FindAll array:", hex(array.value or 0), flush=True)

oleaut = ctypes.windll.oleaut32
lower = ctypes.c_long()
upper = ctypes.c_long()
oleaut.SafeArrayGetLBound(array, 1, ctypes.byref(lower))
oleaut.SafeArrayGetUBound(array, 1, ctypes.byref(upper))
print("root children count:", upper.value - lower.value + 1, flush=True)

# GetCurrentPropertyValue at ELEMENT slot 10: (propertyId, VARIANT*)
variant = uia_native._VARIANT()
uia_native._call(
    int(root_ptr.value), 10, "GetCurrentPropertyValue",
    (ctypes.c_int, ctypes.POINTER(uia_native._VARIANT)),
    (uia_native.UIA_ProcessId, ctypes.byref(variant)),
)
print("root ProcessId variant vt:", hex(variant.vt), "i4:", variant.u.i4, flush=True)
oleaut.VariantClear(ctypes.byref(variant))

# property getters at the DISCOVERED offsets (+2)
name_ptr = ctypes.c_void_p()
uia_native._call(
    int(root_ptr.value), 23, "CurrentName",
    (ctypes.POINTER(ctypes.c_void_p),), (ctypes.byref(name_ptr),),
)
if name_ptr.value:
    text = ctypes.c_wchar_p(name_ptr.value).value or ""
    print("root name (slot 23):", repr(text), flush=True)
    oleaut.SysFreeString(ctypes.c_void_p(name_ptr.value))
else:
    print("root name: (empty BSTR)", flush=True)

print("VERIFICATION DONE", flush=True)
