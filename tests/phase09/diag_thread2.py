
import ctypes, ctypes.wintypes as wt, sys, threading, time, traceback
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
_WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
_LRESULT = ctypes.c_ssize_t
out = []
WNDPROC = _WINFUNCTYPE(_LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
def proc(h, m, w, l):
    if m == 0x0002: user32.PostQuitMessage(0)
    return user32.DefWindowProcW(h, m, w, l)

def run():
    try:
        ref = WNDPROC(proc)
        class WC(ctypes.Structure):
            _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                        ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
                        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]
        hinst = kernel32.GetModuleHandleW(None)
        out.append(f"hinst={hinst}")
        wc = WC(); wc.lpfnWndProc = ref; wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(0, 32512)
        wc.lpszClassName = "NexusThrDiag"
        atom = user32.RegisterClassW(ctypes.byref(wc))
        out.append(f"atom={atom} gle={kernel32.GetLastError()}")
        rect = wt.RECT()
        spi = user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        out.append(f"spi={spi} work={rect.right},{rect.bottom}")
        hwnd = user32.CreateWindowExW(
            0x00080000 | 0x00000008 | 0x00000080, "NexusThrDiag", "NEXUS Overlay",
            0x80000000 | 0x10000000,
            rect.right-280-24, rect.bottom-128-24, 280, 128, 0, 0, hinst, 0)
        out.append(f"hwnd={hwnd} gle={kernel32.GetLastError()}")
        out.append(f"layered={user32.SetLayeredWindowAttributes(hwnd, 0, 235, 2)}")
        font = gdi32.GetStockObject(17)
        btn = user32.CreateWindowExW(0, "BUTTON", "Pause",
            0x40000000 | 0x10000000 | 0x00000001, 24, 72, 110, 34, hwnd, 101, hinst, 0)
        out.append(f"btn={btn} gle={kernel32.GetLastError()}")
        out.append(f"find={user32.FindWindowW('NexusThrDiag', None)}")
        out.append(f"alive-marker")
        time.sleep(2.0)
        out.append(f"find-after-2s={user32.FindWindowW('NexusThrDiag', None)}")
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW("NexusThrDiag", hinst)
    except BaseException:
        out.append("EXC:\n" + traceback.format_exc())

t = threading.Thread(target=run, daemon=True)
t.start()
t.join(15)
print("\n".join(out))
