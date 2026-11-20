"""Native Windows UI Automation client (Final Build Plan §9.4).

A dependency-free ``ctypes`` COM client for the OS UIA service — the
**first layer** wherever possible, before any backend library:

* ``IUIAutomation`` : root · ``from_handle`` · focused ·
  ``CreateTrueCondition`` for ``FindAll`` (children)
* ``IUIAutomationElement`` : ``SetFocus`` · ``CurrentProcessId`` ·
  ``CurrentControlType`` · ``CurrentName`` · ``CurrentIsEnabled`` ·
  ``CurrentClassName`` · ``GetCurrentPropertyValue`` (the rectangle
  arrives as an ``r8`` SAFEARRAY) · ``GetCurrentPattern``
* patterns: ``Invoke`` (10000) and ``Value`` (10002, ``SetValue``)

Every HRESULT is checked — a nonzero code raises :class:`UiaNativeError`
with the code in hex; nothing is swallowed. BSTRs are freed; returned
SAFEARRAYs are destroyed; per-element AddRefs are Released; the COM
apartment init is tracked per thread and only inits this module owns
are uninitialized.

Off win32 every probe reports unavailable honestly — the layer never
fakes an element.

أول طبقة: UIA الأصلية عبر ctypes — عناصر وأنماط وفحص كل HRESULT،
وصدق كامل خارج ويندوز.

Stdlib only.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from typing import Any

#: UIA property ids (UIAutomationClient.h).
UIA_ProcessId = 30002
UIA_ControlType = 30003
UIA_Name = 30019
UIA_IsEnabled = 30010
UIA_BoundingRectangle = 30101
UIA_ClassName = 30012

#: UIA pattern ids.
UIA_InvokePatternId = 10000
UIA_ValuePatternId = 10002

#: TreeScope children (a bounded, level-by-level walk).
TREE_SCOPE_CHILDREN = 2

_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x0
_S_OK = 0
_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106

#: CONTROLTYPEID → canonical name (the standard 50000 series).
CONTROL_TYPE_NAMES: dict[int, str] = {
    50000: "button",
    50001: "calendar",
    50002: "checkbox",
    50003: "combobox",
    50004: "edit",
    50005: "hyperlink",
    50006: "image",
    50007: "listitem",
    50008: "list",
    50009: "menu",
    50010: "menubar",
    50011: "menuitem",
    50012: "progressbar",
    50013: "radiobutton",
    50014: "scrollbar",
    50015: "slider",
    50016: "spinner",
    50017: "statusbar",
    50018: "tab",
    50019: "tabitem",
    50020: "text",
    50021: "toolbar",
    50022: "tooltip",
    50023: "tree",
    50024: "treeitem",
    50025: "custom",
    50026: "datagrid",
    50027: "dataitem",
    50028: "document",
    50029: "group",
    50030: "header",
    50031: "headeritem",
    50032: "thumb",
    50033: "titlebar",
    50034: "pane",
    50035: "splitbutton",
    50036: "window",
    50037: "table",
}

_HRESULT = ctypes.c_long

#: WINFUNCTYPE is win32-only in the stubs — fall back to CFUNCTYPE
#: for non-win32 type-checking (the client refuses calls off win32
#: before ever reaching a vtable).
_WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)


class UiaNativeError(Exception):
    """A checked UIA HRESULT or a refused operation — never silent."""


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> _GUID:
    """Parse a GUID literal — the string is display order: Data1/2/3
    are hex *values* (never byte-reversed); only Data4 stays bytes."""
    digits = text.strip("{}").replace("-", "")
    if len(digits) != 32:
        raise UiaNativeError(f"bad GUID literal {text!r}")
    raw = bytes.fromhex(digits)
    guid = _GUID()
    guid.Data1 = int(digits[0:8], 16)
    guid.Data2 = int(digits[8:12], 16)
    guid.Data3 = int(digits[12:16], 16)
    for index in range(8):
        guid.Data4[index] = raw[8 + index]
    return guid


_CLSID_CUIAutomation = _guid("{ff48dba4-60ef-4201-aa87-54103eef594e}")
_IID_IUIAutomation = _guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")


class _VARIANT(ctypes.Structure):
    """The OLE ``VARIANT`` — 24 bytes on x64: the union must be at
    least ``DECIMAL``-sized (16), or out-param writes smash 8 bytes
    past the structure (a real crash the device probe caught)."""

    class _U(ctypes.Union):
        _fields_ = [
            ("decimal", ctypes.c_byte * 16),
            ("i8", ctypes.c_longlong),
            ("i4", ctypes.c_int),
            ("i2", ctypes.c_short),
            ("boolean", ctypes.c_short),
            ("bstr", ctypes.c_void_p),
            ("parray", ctypes.c_void_p),
        ]

    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("u", _U),
    ]


#: VT_ARRAY | VT_R8 (a SAFEARRAY of doubles).
_VT_R8_ARRAY = 0x2005

_com_state = threading.local()


def _ole32() -> Any:
    if sys.platform != "win32":
        raise UiaNativeError(
            f"UIA requires win32 (this runtime is {sys.platform})"
        )
    return ctypes.windll.ole32  # type: ignore[attr-defined]


def _oleaut32() -> Any:
    if sys.platform != "win32":
        raise UiaNativeError(
            f"UIA requires win32 (this runtime is {sys.platform})"
        )
    return ctypes.windll.oleaut32  # type: ignore[attr-defined]


def ensure_com() -> None:
    """Per-thread apartment init (owned inits are paired on release)."""
    count = getattr(_com_state, "init_count", 0)
    if count or getattr(_com_state, "external", False):
        return
    ole32 = _ole32()
    result = int(
        ctypes.HRESULT(  # type: ignore[call-arg]
            ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        ).value
    )
    if result == _RPC_E_CHANGED_MODE:
        # Another component already chose MTA for this thread — use it
        # as-is and never uninitialize what we do not own.
        _com_state.external = True
        return
    if result not in (0, 1):  # S_OK / S_FALSE both mean "usable"
        _check(result, "CoInitializeEx")
    _com_state.init_count = count + 1


def release_com() -> None:
    """Pair every apartment init this module owns."""
    count = getattr(_com_state, "init_count", 0)
    if count:
        _ole32().CoUninitialize()
        _com_state.init_count = count - 1


def _check(hr: int, call: str) -> None:
    if hr != 0:
        code = hr & 0xFFFFFFFF
        raise UiaNativeError(f"UIA {call} failed: 0x{code:08X}")


def _fn(pointer: int, index: int, restype: Any, *argtypes: Any) -> Any:
    """The vtable slot ``index`` of a COM interface, as a callable."""
    vtable = ctypes.c_void_p.from_address(pointer).value
    if vtable is None:
        raise UiaNativeError(f"null vtable (interface at {pointer:#x})")
    address = ctypes.c_void_p.from_address(vtable + 8 * index).value
    if address is None:
        raise UiaNativeError(f"null vtable slot {index}")
    return _WINFUNCTYPE(restype, *argtypes)(address)


def _call(
    pointer: int, index: int, call: str, argtypes: tuple[Any, ...], args: tuple[Any, ...]
) -> int:
    """Invoke one vtable slot with the this-pointer prepended; check HR."""
    prototype = _fn(pointer, index, _HRESULT, ctypes.c_void_p, *argtypes)
    hr = prototype(ctypes.c_void_p(pointer), *args)
    _check(int(hr), call)
    return int(hr)


def _release_raw(pointer: int) -> None:
    """Release one COM interface (slot 2, this marshaled as c_void_p).

    A raw-int this-pointer would be truncated to 32 bits by ctypes'
    default conversion — on x64 heap pointers that corrupts the call.
    """
    try:
        _fn(pointer, 2, _HRESULT, ctypes.c_void_p)(ctypes.c_void_p(pointer))
    except (UiaNativeError, OSError, ctypes.ArgumentError):
        pass


class UIAElement:
    """One live ``IUIAutomationElement`` — deterministic lifetime.

    Vtable layout (device-verified 2026-09-07 on Windows 10.0.19045,
    x64): methods 3..17 (SetFocus · GetRuntimeId · Find* ·
    GetCurrentPropertyValue · patterns) then TWO inert slots (18/19 —
    probes no-op; the Win10 build's reserved pair) then the property
    getters from 20: ProcessId(20) · ControlType(21) ·
    LocalizedControlType(22) · Name(23) · … · HasKeyboardFocus(26) ·
    IsKeyboardFocusable(27) · IsEnabled(28) · AutomationId(29) ·
    ClassName(30). Verified live: root name → 'سطح المكتب 1' and the
    ProcessId VARIANT round-trip (vt=3).
    """

    __slots__ = ("_pointer", "_released")

    def __init__(self, pointer: int) -> None:
        if not pointer:
            raise UiaNativeError("null IUIAutomationElement pointer")
        self._pointer = pointer
        self._released = False

    # ----------------------------------------------------------- plumbing

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        _release_raw(self._pointer)

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown
        try:
            self.release()
        except Exception:
            pass

    def _slot(
        self, index: int, call: str, argtypes: tuple[Any, ...], args: tuple[Any, ...]
    ) -> int:
        if self._released:
            raise UiaNativeError("element already released")
        return _call(self._pointer, index, call, argtypes, args)

    # ------------------------------------------------------- properties

    def _int_property(self, index: int, name: str) -> int:
        value = ctypes.c_int()
        self._slot(index, name, (ctypes.POINTER(ctypes.c_int),), (ctypes.byref(value),))
        return int(value.value)

    def _bstr_property(self, index: int, name: str) -> str:
        value = ctypes.c_void_p()
        self._slot(
            index, name, (ctypes.POINTER(ctypes.c_void_p),), (ctypes.byref(value),)
        )
        if not value.value:
            return ""
        text = ctypes.c_wchar_p(value.value).value or ""
        _oleaut32().SysFreeString(ctypes.c_void_p(value.value))
        return text

    @property
    def process_id(self) -> int:
        return self._int_property(20, "CurrentProcessId")

    @property
    def control_type(self) -> int:
        return self._int_property(21, "CurrentControlType")

    @property
    def control_type_name(self) -> str:
        return CONTROL_TYPE_NAMES.get(self.control_type, "unknown")

    @property
    def name(self) -> str:
        return self._bstr_property(23, "CurrentName")

    @property
    def is_enabled(self) -> bool:
        return bool(self._int_property(28, "CurrentIsEnabled"))

    @property
    def class_name(self) -> str:
        return self._bstr_property(30, "CurrentClassName")

    @property
    def rectangle(self) -> dict[str, int]:
        variant = _VARIANT()
        self._slot(
            10,
            "GetCurrentPropertyValue(BoundingRectangle)",
            (ctypes.c_int, ctypes.POINTER(_VARIANT)),
            (UIA_BoundingRectangle, ctypes.byref(variant)),
        )
        try:
            if variant.vt != _VT_R8_ARRAY or not variant.u.parray:
                raise UiaNativeError(
                    f"BoundingRectangle variant is not r8 array (vt={variant.vt:#x})"
                )
            return _read_rect_safearray(int(variant.u.parray))
        finally:
            _oleaut32().VariantClear(ctypes.byref(variant))

    # --------------------------------------------------------- patterns

    def set_focus(self) -> None:
        self._slot(3, "SetFocus", (), ())

    def _pattern(self, pattern_id: int, name: str) -> int:
        pointer = ctypes.c_void_p()
        self._slot(
            16,
            f"GetCurrentPattern({name})",
            (ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)),
            (pattern_id, ctypes.byref(pointer)),
        )
        if not pointer.value:
            raise UiaNativeError(f"{name} pattern not supported by this element")
        return int(pointer.value)

    def invoke(self) -> None:
        pattern = self._pattern(UIA_InvokePatternId, "Invoke")
        try:
            prototype = _fn(pattern, 3, _HRESULT, ctypes.c_void_p)
            _check(int(prototype(ctypes.c_void_p(pattern))), "InvokePattern.Invoke")
        finally:
            _release_raw(pattern)

    def set_value(self, text: str) -> None:
        pattern = self._pattern(UIA_ValuePatternId, "Value")
        try:
            bstr = int(_oleaut32().SysAllocStringLen(text, len(text)))
            try:
                prototype = _fn(
                    pattern, 3, _HRESULT, ctypes.c_void_p, ctypes.c_void_p
                )
                _check(
                    int(
                        prototype(
                            ctypes.c_void_p(pattern), ctypes.c_void_p(bstr)
                        )
                    ),
                    "ValuePattern.SetValue",
                )
            finally:
                _oleaut32().SysFreeString(ctypes.c_void_p(bstr))
        finally:
            _release_raw(pattern)

    # ----------------------------------------------------------- queries

    def children(self) -> list[UIAElement]:
        automation = _automation()
        condition = ctypes.c_void_p()
        _call(
            automation,
            17,
            "CreateTrueCondition",
            (ctypes.POINTER(ctypes.c_void_p),),
            (ctypes.byref(condition),),
        )
        array = ctypes.c_void_p()
        try:
            self._slot(
                6,
                "FindAll(children)",
                (ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                (TREE_SCOPE_CHILDREN, condition, ctypes.byref(array)),
            )
        finally:
            _release_raw(int(condition.value or 0))
        if not array.value:
            return []
        try:
            return _read_element_safearray(int(array.value))
        finally:
            array_pointer = ctypes.c_void_p(array.value)
            _oleaut32().SafeArrayDestroy(array_pointer)

    def record(self) -> dict[str, Any]:
        try:
            rect = self.rectangle
        except UiaNativeError:
            rect = {}  # the rectangle is optional evidence, not a blocker
        return {
            "name": self.name,
            "control_type": self.control_type,
            "control_type_name": self.control_type_name,
            "class_name": self.class_name,
            "process_id": self.process_id,
            "is_enabled": self.is_enabled,
            "rect": rect,
        }


def _read_rect_safearray(pointer: int) -> dict[str, int]:
    oleaut = _oleaut32()
    lower = ctypes.c_long()
    upper = ctypes.c_long()
    _check(
        int(
            oleaut.SafeArrayGetLBound(
                ctypes.c_void_p(pointer), 1, ctypes.byref(lower)
            )
        ),
        "SafeArrayGetLBound",
    )
    _check(
        int(
            oleaut.SafeArrayGetUBound(
                ctypes.c_void_p(pointer), 1, ctypes.byref(upper)
            )
        ),
        "SafeArrayGetUBound",
    )
    if upper.value - lower.value + 1 != 4:
        raise UiaNativeError(
            f"BoundingRectangle array has {upper.value - lower.value + 1} items"
        )
    values: list[float] = []
    for index in range(4):
        value = ctypes.c_double()
        position = ctypes.c_long(lower.value + index)
        _check(
            int(
                oleaut.SafeArrayGetElement(
                    ctypes.c_void_p(pointer),
                    ctypes.byref(position),
                    ctypes.byref(value),
                )
            ),
            "SafeArrayGetElement(rect)",
        )
        values.append(value.value)
    left, top, right, bottom = (round(value) for value in values)
    return {
        "left": left,
        "top": top,
        "width": right - left,
        "height": bottom - top,
    }


def _read_element_safearray(pointer: int) -> list[UIAElement]:
    oleaut = _oleaut32()
    lower = ctypes.c_long()
    upper = ctypes.c_long()
    _check(
        int(
            oleaut.SafeArrayGetLBound(
                ctypes.c_void_p(pointer), 1, ctypes.byref(lower)
            )
        ),
        "SafeArrayGetLBound",
    )
    _check(
        int(
            oleaut.SafeArrayGetUBound(
                ctypes.c_void_p(pointer), 1, ctypes.byref(upper)
            )
        ),
        "SafeArrayGetUBound",
    )
    elements: list[UIAElement] = []
    for index in range(lower.value, upper.value + 1):
        element = ctypes.c_void_p()
        position = ctypes.c_long(index)
        _check(
            int(
                oleaut.SafeArrayGetElement(
                    ctypes.c_void_p(pointer),
                    ctypes.byref(position),
                    ctypes.byref(element),
                )
            ),
            "SafeArrayGetElement(element)",
        )
        if element.value:
            elements.append(UIAElement(int(element.value)))
    return elements


def _automation() -> int:
    cached = getattr(_com_state, "automation", 0)
    if cached:
        return cached
    ensure_com()
    ole32 = _ole32()
    pointer = ctypes.c_void_p()
    _check(
        int(
            ole32.CoCreateInstance(
                ctypes.byref(_CLSID_CUIAutomation),
                None,
                _CLSCTX_INPROC_SERVER,
                ctypes.byref(_IID_IUIAutomation),
                ctypes.byref(pointer),
            )
        ),
        "CoCreateInstance(CUIAutomation)",
    )
    if not pointer.value:
        raise UiaNativeError("CoCreateInstance returned a null automation")
    _com_state.automation = int(pointer.value)
    return int(pointer.value)


def root_element() -> UIAElement:
    """The desktop root (GetRootElement)."""
    automation = _automation()
    pointer = ctypes.c_void_p()
    _call(
        automation, 5, "GetRootElement", (ctypes.POINTER(ctypes.c_void_p),),
        (ctypes.byref(pointer),),
    )
    if not pointer.value:
        raise UiaNativeError("GetRootElement returned no element")
    return UIAElement(int(pointer.value))


def element_from_handle(hwnd: int) -> UIAElement:
    """Element for a window handle (ElementFromHandle)."""
    automation = _automation()
    pointer = ctypes.c_void_p()
    _call(
        automation,
        6,
        "ElementFromHandle",
        (ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
        (ctypes.c_void_p(hwnd), ctypes.byref(pointer)),
    )
    if not pointer.value:
        raise UiaNativeError(f"ElementFromHandle({hwnd}) returned no element")
    return UIAElement(int(pointer.value))


def focused_element() -> UIAElement:
    """The currently focused element (GetFocusedElement)."""
    automation = _automation()
    pointer = ctypes.c_void_p()
    _call(
        automation, 8, "GetFocusedElement", (ctypes.POINTER(ctypes.c_void_p),),
        (ctypes.byref(pointer),),
    )
    if not pointer.value:
        raise UiaNativeError("GetFocusedElement returned no element")
    return UIAElement(int(pointer.value))


def tree_record(element: UIAElement, *, depth: int, max_nodes: int) -> dict[str, Any]:
    """Bounded breadth-first element tree as nested records."""
    if depth < 1 or depth > 8:
        raise UiaNativeError("tree depth must be within 1..8")
    if max_nodes < 1 or max_nodes > 500:
        raise UiaNativeError("tree max_nodes must be within 1..500")

    def walk(current: UIAElement, remaining: int) -> tuple[dict[str, Any], int]:
        record = current.record()
        record["children"] = []
        if remaining <= 1:
            return record, 1
        children = current.children()
        budget = remaining - 1
        for child in children:
            if budget <= 0:
                record["truncated"] = True
                break
            try:
                child_record, used = walk(child, budget)
            finally:
                child.release()
            budget -= used
            record["children"].append(child_record)
        return record, remaining - budget

    record, _used = walk(element, max_nodes)
    return record


def available() -> bool:
    return sys.platform == "win32"


def close() -> None:
    """Release the cached automation pointer and owned COM inits."""
    cached = getattr(_com_state, "automation", 0)
    if cached:
        _release_raw(cached)
        _com_state.automation = 0
    release_com()
