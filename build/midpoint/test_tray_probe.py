# -*- coding: utf-8 -*-
"""tray probe — isolate WHY the production tray thread died + registry rc=5.
Three isolated strategies + registry diagnosis, all recorded to JSON.
Fast (no rebuild): pytest trigger, ~8s total.
"""
from __future__ import annotations

import ctypes
import json
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent          # build\midpoint
sys.path.insert(0, str(HERE))

OUT = HERE / "results" / "tray_probe.json"

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
WM_APP_TRAY = 0x8001
PM_REMOVE = 1
MF_STRING = 0x0
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, ctypes.c_uint,
                             ctypes.c_longlong, ctypes.c_longlong)


class _NID(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
        ("uID", ctypes.c_uint), ("uFlags", ctypes.c_uint),
        ("uCallbackMessage", ctypes.c_uint), ("hIcon", wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128), ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD), ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", ctypes.c_uint), ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class _WC(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", ctypes.c_void_p), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


def _load_hicon(path: Path, size: int) -> int:
    try:
        return int(user32.LoadImageW(None, str(path), IMAGE_ICON, size, size,
                                     LR_LOADFROMFILE) or 0)
    except BaseException as exc:
        return 0


def mk_wc(class_name, proc):
    wc = _WC()
    wc.lpfnWndProc = proc
    wc.lpszClassName = class_name
    wc.hInstance = kernel32.GetModuleHandleW(None)
    return wc


# ---------------- strategy A: exactly the current ProductionTray (bound method)
def strat_a(paths, out):
    import nexus_ui  # the deployed v27 module

    t = nexus_ui.ProductionTray(paths, dispatch=lambda aid: out.setdefault("dispatched", []).append(aid))
    t.start()
    time.sleep(2.5)
    out["verdicts"] = dict(t.verdicts)
    out["run_err"] = t._run_err
    out["hwnd_alive"] = bool(t.hwnd)
    t.stop(timeout=3)
    out["delete_ok_after_stop"] = t.verdicts.get("delete_ok")
    out["run_err_after_stop"] = t._run_err


# ------------- strategy B: C wndproc (DefWindowProcW) + PeekMessage filter
def strat_b(paths, out):
    res = {"add": None, "modify": None, "delete": None, "saw_callback": None,
           "err": None}
    res["hicon32"] = _load_hicon(paths["ready"], 32)
    res["hicon16"] = _load_hicon(paths["ready"], 16)

    def body():
        try:
            proc = WNDPROC(user32.DefWindowProcW)      # C callback — no Python
            wc = mk_wc("NEXUSProbeB", proc)
            ok_reg = bool(user32.RegisterClassW(ctypes.byref(wc)))
            res["register"] = ok_reg
            if not ok_reg:
                res["err"] = f"RegisterClassW gle={ctypes.GetLastError()}"
                return
            hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "probeB", 0,
                                          0, 0, 0, 0, None, None,
                                          wc.hInstance, None)
            res["hwnd"] = bool(hwnd)
            if not hwnd:
                res["err"] = f"CreateWindowExW gle={ctypes.GetLastError()}"
                return
            nid = _NID()
            nid.cbSize = ctypes.sizeof(_NID)
            nid.hWnd = hwnd
            nid.uID = 99
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_APP_TRAY
            nid.hIcon = res["hicon32"] or res["hicon16"]
            nid.szTip = "probeB — ready"
            res["add"] = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
            nid.szTip = "probeB — working"
            res["modify"] = bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid)))
            msg = wintypes.MSG()
            end = time.time() + 2.0
            saw = None
            while time.time() < end:
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_APP_TRAY:
                        saw = int(msg.lParam)
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.02)
            res["saw_callback"] = saw
            res["delete"] = bool(shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid)))
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(wc.lpszClassName, wc.hInstance)
        except BaseException as exc:
            res["err"] = f"{type(exc).__name__}: {exc}"

    th = threading.Thread(target=body, daemon=True)
    th.start()
    th.join(timeout=8)
    out["strategyB"] = res


# ------------- strategy C: bound-method wndproc in MAIN thread (no tk)
def strat_c(paths, out):
    res = {"add": None, "modify": None, "delete": None, "err": None,
           "callback_seen": None}
    holder = {}

    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_APP_TRAY:
            res["callback_seen"] = int(lparam)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    try:
        proc = WNDPROC(wndproc)
        holder["proc"] = proc
        wc = mk_wc("NEXUSProbeC", proc)
        res["register"] = bool(user32.RegisterClassW(ctypes.byref(wc)))
        hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "probeC", 0,
                                      0, 0, 0, 0, None, None, wc.hInstance, None)
        res["hwnd"] = bool(hwnd)
        nid = _NID()
        nid.cbSize = ctypes.sizeof(_NID)
        nid.hWnd = hwnd
        nid.uID = 98
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_APP_TRAY
        nid.hIcon = _load_hicon(paths["ready"], 32)
        nid.szTip = "probeC — ready"
        res["add"] = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
        msg = wintypes.MSG()
        end = time.time() + 1.5
        while time.time() < end:
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.02)
        res["delete"] = bool(shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid)))
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW(wc.lpszClassName, wc.hInstance)
    except BaseException as exc:
        res["err"] = f"{type(exc).__name__}: {exc}"
    out["strategyC"] = res


# ---------------- registry diagnosis
def reg_probe(out):
    HKEY_CURRENT_USER = 0x80000001
    KEY_QUERY_VALUE, KEY_SET_VALUE = 0x1, 0x2
    REG_SZ = 1
    adv = ctypes.windll.advapi32
    r = {}
    h = wintypes.HKEY()
    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    rc = adv.RegOpenKeyExW(HKEY_CURRENT_USER, run_key, 0,
                           KEY_SET_VALUE | KEY_QUERY_VALUE, ctypes.byref(h))
    r["open_rc"] = rc
    if rc == 0:
        buf = ctypes.create_unicode_buffer("NEXUS_probe_test")
        r["set_rc"] = adv.RegSetValueExW(h, "NEXUS_probe_test", 0, REG_SZ, buf,
                                         (len("NEXUS_probe_test") + 1) * 2)
        r["del_rc"] = adv.RegDeleteValueW(h, "NEXUS_probe_test")
        ctypes.windll.advapi32.RegCloseKey(h)
    # startup folder fallback feasibility
    try:
        startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
        r["startup_dir_exists"] = startup.is_dir()
        probe = startup / "_nexus_probe.tmp"
        probe.write_text("probe", encoding="utf-8")
        r["startup_write_ok"] = probe.is_file()
        probe.unlink(missing_ok=True)
    except BaseException as exc:
        r["startup_err"] = f"{type(exc).__name__}: {exc}"
    out["registry"] = r


import os  # noqa: E402  (after consts — probe file, not product code)


def test_tray_probe() -> None:
    out: dict = {"python": sys.version.split()[0],
                 "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    assets = HERE.parent.parent / "assets"
    paths = {st: assets / f"nexus_{st}.ico" for st in ("ready", "working", "offline")}
    out["ico_exists"] = {st: p.is_file() for st, p in paths.items()}

    # strategy B first (isolated C flow — the cleanest signal)
    strat_b(paths, out)
    time.sleep(0.5)
    # strategy C (main thread, python callback)
    strat_c(paths, out)
    time.sleep(0.5)
    # strategy A (current production class — last so its class-name is fresh)
    try:
        strat_a(paths, out)
    except BaseException as exc:
        out["strategyA_err"] = f"{type(exc).__name__}: {exc}"
    reg_probe(out)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False)[:2000])
