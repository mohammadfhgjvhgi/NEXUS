
import sys, time, ctypes
sys.path.insert(0, r"M:\NEXUS")
from nexus.windows.overlay import OverlayController, NativeOverlay
user32 = ctypes.windll.user32

LOG = open(r"M:\NEXUS\proofs\overlay_msgs.log", "w", encoding="utf-8")
SPECIAL = {0x0001:"WM_CREATE",0x0002:"WM_DESTROY",0x0010:"WM_CLOSE",0x000F:"WM_PAINT",
           0x0014:"WM_ERASEBKGND",0x0018:"WM_SHOWWINDOW",0x001C:"WM_ACTIVATEAPP",
           0x0085:"WM_NCPAINT",0x8001:"WM_APP_STATE",0x0086:"WM_NCACTIVATE",0x0006:"WM_ACTIVATE",
           0x0005:"WM_SIZE",0x0003:"WM_MOVE",0x001A:"WM_SETTINGCHANGE",0x0011:"WM_QUERYENDSESSION"}

orig_proc = NativeOverlay._wndproc
def logged(self, hwnd, message, wparam, lparam):
    name = SPECIAL.get(message, hex(message))
    LOG.write(f"msg {name} hwnd={hwnd} wp={wparam} lp={lparam}\n"); LOG.flush()
    result = orig_proc(self, hwnd, message, wparam, lparam)
    if message in (0x0002, 0x0010):
        LOG.write(f"  -> handled {name}, returning {result}\n"); LOG.flush()
    return result
NativeOverlay._wndproc = logged

orig_run = NativeOverlay._run
import traceback
def safe_run(self):
    try:
        orig_run(self)
    except BaseException:
        LOG.write("RUN EXC:\n"+traceback.format_exc()); LOG.flush()
    LOG.write("run() returned (thread exiting)\n"); LOG.flush()
NativeOverlay._run = safe_run

ctl = OverlayController()
ctl.begin("diag")
time.sleep(2.5)
backend = ctl._backend
LOG.write(f"alive={backend._alive} hwnd={backend._hwnd} thread_alive={backend._thread.is_alive() if backend._thread else None}\n")
find = user32.FindWindowW("NexusOverlayWnd", None)
LOG.write(f"find={find}\n")
LOG.close()
ctl.shutdown()
time.sleep(0.5)
print(open(r"M:\NEXUS\proofs\overlay_msgs.log", encoding="utf-8").read()[:3000])
