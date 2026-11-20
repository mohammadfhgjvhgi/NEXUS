import sys, traceback
sys.path.insert(0, r"M:\NEXUS")
from nexus.computer import uia_native
print("step 1: available =", uia_native.available())
try:
    uia_native.ensure_com()
    print("step 2: ensure_com OK (count =", getattr(uia_native._com_state, "init_count", "?"),
          "external =", getattr(uia_native._com_state, "external", False), ")")
except Exception:
    print("step 2 FAILED:"); traceback.print_exc(); sys.exit(1)
try:
    a = uia_native._automation()
    print("step 3: automation ptr =", hex(a))
except Exception:
    print("step 3 FAILED:"); traceback.print_exc(); sys.exit(1)
try:
    e = uia_native.focused_element()
    try:
        rec = e.record()
        print("step 4: focused record =", rec)
    finally:
        e.release()
except Exception:
    print("step 4 FAILED:"); traceback.print_exc()
