
import sys, time, traceback
sys.path.insert(0, r"M:\NEXUS")
from nexus.windows.overlay import OverlayController, NativeOverlay
import ctypes
user32 = ctypes.windll.user32

orig_run = NativeOverlay._run
def safe_run(self):
    try:
        orig_run(self)
    except BaseException:
        with open(r"M:\NEXUS\proofs\overlay_thread_exc.txt", "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
NativeOverlay._run = safe_run

ctl = OverlayController()
print("backend kind:", ctl.backend_kind)
print("begin:", ctl.begin("diag"))
time.sleep(2.0)
backend = ctl._backend
print("alive:", backend._alive, "hwnd:", backend._hwnd, "thread:", backend._thread)
print("find:", user32.FindWindowW("NexusOverlayWnd", None))
print("state:", ctl.state)
print("end:", ctl.end())
time.sleep(0.6)
print("after end find:", user32.FindWindowW("NexusOverlayWnd", None))
import pathlib
exc = pathlib.Path(r"M:\NEXUS\proofs\overlay_thread_exc.txt")
print("thread exc:", exc.read_text(encoding="utf-8")[:1200] if exc.exists() else "(none)")
