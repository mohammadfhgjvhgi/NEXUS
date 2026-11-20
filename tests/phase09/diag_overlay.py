
import ctypes, ctypes.wintypes as wt, sys, threading, traceback
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
out = []
WNDPROC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
def proc(h, m, w, l):
    if m == 0x0002: user32.PostQuitMessage(0)
    return user32.DefWindowProcW(h, m, w, l)
ref = WNDPROC(proc)
class WC(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]
hinst = kernel32.GetModuleHandleW(None)
out.append(f"hinstance={hinst}")
wc = WC(); wc.lpfnWndProc = ref; wc.hInstance = hinst; wc.lpszClassName = "NexusDiagWnd"
atom = user32.RegisterClassW(ctypes.byref(wc))
out.append(f"atom={atom} err={kernel32.GetLastError()}")
try:
    hwnd = user32.CreateWindowExW(0x00080000|0x00000008|0x00000080, "NexusDiagWnd", "t",
        0x80000000|0x10000000, 100, 100, 280, 128, 0, 0, hinst, 0)
    out.append(f"hwnd={hwnd} err={kernel32.GetLastError()}")
    out.append(f"found={user32.FindWindowW('NexusDiagWnd', None)}")
    out.append(f"layered={user32.SetLayeredWindowAttributes(hwnd, 0, 235, 2)}")
    if hwnd:
        user32.DestroyWindow(hwnd)
except Exception as e:
    out.append("EXC: " + repr(e))
user32.UnregisterClassW("NexusDiagWnd", hinst)
print("\n".join(out))
