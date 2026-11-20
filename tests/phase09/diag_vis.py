
import sys, time, ctypes
sys.path.insert(0, r"M:\NEXUS")
from nexus.tools import build_tool_system
from nexus.windows import build_overlay
user32 = ctypes.windll.user32

_reg, router, _a, _r = build_tool_system(native=True, computer=True, mcp_servers=())
from nexus.computer import build_computer_runtime
computer = build_computer_runtime(router)

class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
work = RECT()
user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)
ax = work.r - 280 - 24; ay = work.b - 128 - 24
print("anchor:", ax, ay, "work:", work.l, work.t, work.r, work.b)

ctl = build_overlay()
# capture the exact overlay rect BEFORE (no window yet)
computer.screens("screenshot", x=ax-10, y=ay-10, w=300, h=148, path=r"M:\NEXUS\proofs\vis_before.png")
ctl.begin("vis diag")
time.sleep(1.5)
hwnd = user32.FindWindowW("NexusOverlayWnd", None)
print("hwnd:", hwnd)
rect = RECT(); user32.GetWindowRect(hwnd, ctypes.byref(rect))
print("rect:", rect.l, rect.t, rect.r, rect.b, "size:", rect.r-rect.l, rect.b-rect.t)
computer.screens("screenshot", x=ax-10, y=ay-10, w=300, h=148, path=r"M:\NEXUS\proofs\vis_after.png")
import pathlib
b1 = pathlib.Path(r"M:\NEXUS\proofs\vis_before.png").stat().st_size
b2 = pathlib.Path(r"M:\NEXUS\proofs\vis_after.png").stat().st_size
print("png bytes:", b1, b2, "differ:", b1 != b2)
# also full-screen diff as sanity
computer.screens("screenshot", x=0, y=0, w=400, h=400, path=r"M:\NEXUS\proofs\vis_corner.png")
ctl.shutdown()
time.sleep(0.5)
