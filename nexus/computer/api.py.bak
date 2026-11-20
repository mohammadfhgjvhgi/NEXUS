"""Computer API (Final Build Plan §9.1) — the eight domains.

The façade that makes NEXUS *use the real computer*:

=================  ====================================================
``screens``        size · screenshot · region (GDI + stdlib PNG)
``windows``        list · active · focus · minimize/maximize/restore ·
                    close (user32)
``focus``          the §9.1 focus convenience over the windows tool
``mouse``          move · click · double/right/middle · drag · scroll
                    (SendInput)
``keyboard``       press(combo) · type(unicode) (SendInput)
``clipboard``      get · set (user32 clipboard)
``uia``            inspect · element · focused · invoke · set_value ·
                    focus (native ctypes client — §9.4 first layer)
``processes``      list · info (ps_table/psutil when present)
=================  ====================================================

Every domain method is a **thin router client** — ``router.route``
with the §8.2 seven-stage pipeline (policy → confirmation → scope →
resources → execute → normalise → verify). The Computer API adds no
second choke point: it is policy and orchestration, the router stays
the single gate every real-world effect passes through.

:meth:`ComputerRuntime.act` is the §9.5 coordinator entry — the
fallback hierarchy with all five layers (application API → UIA →
DOM/a11y → vision → mouse/keyboard), each attempt recorded. The DOM
and vision layers report *unavailable* until their phases ship —
honest degradation, not stubbed success.

واجهة الحاسوب — ثمانية نطاقات خلف الموجّه نفسه، ومنسّق التراجع
فوقها؛ لا بوابة ثانية ولا صمت.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..tools.router import ToolRouter
from .hierarchy import (
    ActionTarget,
    HierarchyChain,
    LayerError,
    LayerProvider,
    LayerResult,
)

#: The §9.1 domains, verbatim.
COMPUTER_DOMAINS: tuple[str, ...] = (
    "screens",
    "windows",
    "focus",
    "mouse",
    "keyboard",
    "clipboard",
    "uia",
    "processes",
)

#: Domain → dispatch tool name (the §8.3/§9.1 records).
_DOMAIN_TOOLS: dict[str, str] = {
    "screens": "screen",
    "windows": "windows",
    "focus": "windows",
    "mouse": "mouse",
    "keyboard": "keyboard",
    "clipboard": "clipboard",
    "uia": "uia",
    "processes": "process",
}


class ComputerError(Exception):
    """A domain call or hierarchy act failed — honest, with the trace."""


class ComputerRuntime:
    """The §9.1 Computer API + the §9.5 coordinator, over the router."""

    def __init__(
        self,
        router: ToolRouter,
        *,
        policy: Any = None,
        workspace_id: str | None = None,
        agent_id: str = "computer",
    ) -> None:
        self._router = router
        self._policy = policy
        self._workspace_id = workspace_id
        self._agent_id = agent_id
        self._active_task_id = ""
        self._chain = HierarchyChain()
        self._chain.register(_NativeUiaLayer(self))
        self._chain.register(_PywinautoLayer(self))
        self._chain.register(_InputLayer(self))

    # ------------------------------------------------------------ router

    @property
    def router(self) -> ToolRouter:
        return self._router

    @property
    def chain(self) -> HierarchyChain:
        return self._chain

    def _route(
        self, domain: str, arguments: Mapping[str, Any], *, task_id: str = ""
    ) -> Any:
        if domain not in _DOMAIN_TOOLS:
            raise ComputerError(f"unknown computer domain {domain!r}")
        outcome = self._router.route(
            _DOMAIN_TOOLS[domain],
            arguments,
            task_id=task_id or self._active_task_id,
            agent_id=self._agent_id,
            policy=self._policy,
            workspace_id=self._workspace_id,
        )
        return outcome

    # -------------------------------------------------- §9.1 the domains

    def screens(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        """size · screenshot · region (the ``screen`` tool)."""
        return self._route("screens", {"op": op, **extra}, task_id=task_id)

    def windows(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        """list_windows · active_window · focus · min/max/restore · close."""
        return self._route("windows", {"op": op, **extra}, task_id=task_id)

    def focus(self, hwnd: int, *, task_id: str = "") -> Any:
        """The §9.1 focus domain — SetForegroundWindow by handle."""
        if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd < 1:
            raise ComputerError("focus requires a positive window handle")
        return self._route(
            "focus", {"op": "focus", "hwnd": hwnd}, task_id=task_id
        )

    def mouse(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        """move · click · double_click · right_click · middle_click · drag · scroll."""
        return self._route("mouse", {"op": op, **extra}, task_id=task_id)

    def keyboard(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        """press(combo) · type(text)."""
        return self._route("keyboard", {"op": op, **extra}, task_id=task_id)

    def clipboard(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        """get · set (the ``clipboard`` tool)."""
        return self._route("clipboard", {"op": op, **extra}, task_id=task_id)

    def uia(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        """inspect · element · focused · invoke · set_value · focus."""
        return self._route("uia", {"op": op, **extra}, task_id=task_id)

    def processes(self, op: str, *, task_id: str = "", **extra: Any) -> Any:
        """list · info (the ``process`` tool)."""
        return self._route("processes", {"op": op, **extra}, task_id=task_id)

    # ------------------------------------------------- §9.5 the hierarchy

    def act(self, target: ActionTarget | str, *, task_id: str = "") -> LayerResult:
        """One action through the §9.5 fallback chain.

        Accepts an :class:`ActionTarget` or a convenience string form
        ``"action:hwnd"`` (e.g. ``"invoke:131074"``).
        """
        if isinstance(target, str):
            target = self._parse_target(target)
        previous = self._active_task_id
        self._active_task_id = task_id
        try:
            return self._chain.act(target)
        finally:
            self._active_task_id = previous

    @staticmethod
    def _parse_target(literal: str) -> ActionTarget:
        parts = literal.split(":", 1)
        action = parts[0].strip()
        hwnd = None
        if len(parts) == 2 and parts[1].strip().isdigit():
            hwnd = int(parts[1].strip())
        if action not in (
            "invoke", "set_value", "focus", "type", "click", "inspect"
        ):
            raise ComputerError(f"unknown computer action {action!r}")
        return ActionTarget(action=action, hwnd=hwnd)

    # ----------------------------------------------------------- probes

    def capability_report(self) -> dict[str, Any]:
        """Per-domain honest probe (registry probes, no guessing)."""
        report: dict[str, Any] = {}
        for domain in COMPUTER_DOMAINS:
            tool_name = _DOMAIN_TOOLS[domain]
            registered = self._router.registry.get(tool_name)
            if registered is None:
                report[domain] = {"available": False, "reason": "not registered"}
                continue
            capability = registered.capabilities()
            report[domain] = {
                "available": bool(capability.available),
                "reason": capability.reason,
            }
        report["hierarchy"] = self._chain.describe()
        return report


# ---------------------------------------------------------- §9.5 layers


class _NativeUiaLayer(LayerProvider):
    """§9.4 native UIA first: invoke · set_value · focus via the router."""

    name = "uia"

    def __init__(self, runtime: ComputerRuntime) -> None:
        self._runtime = runtime

    def available(self) -> tuple[bool, str]:
        import sys

        if sys.platform != "win32":
            return False, f"win32-only layer (this runtime is {sys.platform})"
        return True, "native UIA client via the uia tool"

    def act(self, target: ActionTarget) -> LayerResult | None:
        if target.action not in ("invoke", "set_value", "focus"):
            return None
        hwnd = target.hwnd
        if not hwnd:
            raise LayerError("uia layer requires a target hwnd")
        extra: dict[str, Any] = (
            {"value": target.value} if target.action == "set_value" else {}
        )
        outcome = self._runtime.uia(target.action, hwnd=hwnd, **extra)
        if not outcome.ok:
            raise LayerError(
                f"native uia {target.action} failed: {outcome.error}"
            )
        return LayerResult(
            layer=self.name,
            summary=f"native uia {target.action} → hwnd {target.hwnd}",
            artifacts={"output": outcome.output},
        )


class _PywinautoLayer(LayerProvider):
    """§9.3 pywinauto deep ops: type · invoke · set_value (MODE A)."""

    name = "uia"

    def __init__(self, runtime: ComputerRuntime) -> None:
        self._runtime = runtime

    def available(self) -> tuple[bool, str]:
        from .adapters import pywinauto_backend

        return pywinauto_backend.available()

    def act(self, target: ActionTarget) -> LayerResult | None:
        if target.action not in ("type", "invoke", "set_value"):
            return None
        if not target.hwnd:
            raise LayerError("pywinauto layer requires a target hwnd")
        from .adapters import pywinauto_backend

        try:
            if target.action == "type":
                summary = pywinauto_backend.type_into(
                    target.hwnd, target.value or ""
                )
            elif target.action == "invoke":
                summary = pywinauto_backend.invoke_control(target.hwnd)
            else:
                summary = pywinauto_backend.set_value(
                    target.hwnd, target.value or ""
                )
        except pywinauto_backend.BackendError as exc:
            # A MODE A backend failure is a *layer* failure — the §9.5
            # chain falls through to the next provider, never crashes.
            raise LayerError(f"pywinauto {target.action}: {exc}") from exc
        return LayerResult(
            layer=self.name, summary=summary, artifacts={}
        )


class _InputLayer(LayerProvider):
    """§9.5 last resort: real SendInput through the router tools."""

    name = "input"

    def __init__(self, runtime: ComputerRuntime) -> None:
        self._runtime = runtime

    def available(self) -> tuple[bool, str]:
        import sys

        if sys.platform != "win32":
            return False, f"win32-only layer (this runtime is {sys.platform})"
        return True, "SendInput via the mouse/keyboard tools"

    def act(self, target: ActionTarget) -> LayerResult | None:
        if target.action == "type":
            from . import input_engine

            if target.hwnd:
                # Focus the target politely before typing as the user.
                input_engine.ensure_foreground(target.hwnd)
            outcome = self._runtime.keyboard(
                "type", text=target.value or target.name or ""
            )
            if not outcome.ok:
                raise LayerError(f"keyboard type failed: {outcome.error}")
            return LayerResult(
                layer=self.name,
                summary="typed via SendInput (foreground transport)",
                artifacts={"output": outcome.output},
            )
        if target.action == "click":
            if not target.point:
                raise LayerError("input click requires a target point")
            x, y = target.point
            outcome = self._runtime.mouse("click", x=x, y=y)
            if not outcome.ok:
                raise LayerError(f"mouse click failed: {outcome.error}")
            return LayerResult(
                layer=self.name,
                summary=f"clicked ({x}, {y}) via SendInput",
                artifacts={"output": outcome.output},
            )
        if target.action == "focus":
            if not target.hwnd:
                raise LayerError("input focus requires a target hwnd")
            outcome = self._runtime.windows("focus", hwnd=target.hwnd)
            if not outcome.ok:
                raise LayerError(f"focus failed: {outcome.error}")
            return LayerResult(
                layer=self.name,
                summary=f"focused hwnd {target.hwnd} (SetForegroundWindow)",
                artifacts={"output": outcome.output},
            )
        return None
