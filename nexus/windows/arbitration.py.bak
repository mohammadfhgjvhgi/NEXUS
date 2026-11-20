"""Human/AI Input Arbitration (Final Build Plan §10.3 — Spec §62).

Spec §62 is explicit about the philosophy:

    Not "every user mouse-move pauses the agent" — but
    **window/input ownership**. When the AI works in a task-owned
    window, the user's own work never mixes with it.

So arbitration is *per window*, never per motion. Before NEXUS sends
input to a window (mouse · keyboard · uia · window-focus), the
:class:`InputArbitrator` consults the §10.1 registry:

=================  ===========================================
``USER``          **deny** — the human owns this window's input
``NEXUS``         **allow** — staked by a task/agent
``SHARED``        **allow + coordinated** — both may, flagged
*unknown window*  **deny by default** — the safe posture
=================  ===========================================

: meth:`as_hook` turns the arbitrator into a Phase-6
``pre_tool_call`` veto handler — the §7.1/§7.2 seam the Agent Loop
already consults, so input ownership is enforced at the *loop* level
without a second choke point: the §8.2 router stays the only gate for
effects, the hook decides *whether the loop should even try*.

Coordinate-only mouse calls resolve their window via
``WindowFromPoint`` (win32) — off win32 they degrade honestly to the
unknown-window posture.

تحكيم الإدخال بين الإنسان والآلة — ملكية لكل نافذة لا لكل
حركة، والنقض من خطاف pre_tool_call نفسه.

Stdlib only.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any

from ..harness.hooks import HookContext
from .ownership import InputOwner
from .registry import WindowRegistry

logger = logging.getLogger("nexus.windows")

#: The tools whose input lands in windows the arbitrator guards.
#: (``windows`` included: focus/min/max/close change the human's
#: desktop just as surely as a keystroke.)
INPUT_TOOLS: frozenset[str] = frozenset({"mouse", "keyboard", "uia", "windows"})


@dataclass(frozen=True, slots=True)
class ArbitrationDecision:
    """One request's verdict — always a reason, never a bare bool."""

    allowed: bool
    owner: str  # USER | NEXUS | SHARED | UNKNOWN
    reason: str
    window_id: str = ""
    #: SHARED windows allow the AI *with coordination* — the caller
    # should log/flag the shared access (Spec §62 "لا يختلط العمل").
    coordinated: bool = False
    tool: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "owner": self.owner,
            "reason": self.reason,
            "window_id": self.window_id,
            "coordinated": self.coordinated,
            "tool": self.tool,
        }


def _window_from_point(x: int, y: int) -> int:
    """``WindowFromPoint`` — 0 off win32 (honest unknown posture)."""
    if sys.platform != "win32":
        return 0
    import ctypes

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    return int(user32.WindowFromPoint(_POINT(x, y)))


class InputArbitrator:
    """Decide whether *NEXUS* may send input to a window (§10.3).

    The registry is the truth; the arbitrator adds the posture:
    ``unknown_policy`` is ``"deny"`` by default (an unregistered
    window is presumed the human's) and can be relaxed to ``"allow"``
    for operators who accept that risk.
    """

    def __init__(
        self,
        registry: WindowRegistry,
        *,
        unknown_policy: str = "deny",
    ) -> None:
        if unknown_policy not in ("deny", "allow"):
            raise ValueError(f"unknown_policy must be deny|allow, got {unknown_policy!r}")
        self._registry = registry
        self._unknown_policy = unknown_policy
        #: audit trail of the last decisions (bounded ring).
        self._log: list[ArbitrationDecision] = []

    # ------------------------------------------------------------ decide

    def request(
        self,
        *,
        hwnd: int | None = None,
        point: tuple[int, int] | None = None,
        tool: str = "",
    ) -> ArbitrationDecision:
        """One input request → one verdict (with the reason)."""
        record = None
        if hwnd is not None and hwnd > 0:
            record = self._registry.find(hwnd)
        elif point is not None:
            point_hwnd = _window_from_point(int(point[0]), int(point[1]))
            if point_hwnd > 0:
                record = self._registry.find(point_hwnd)
        if record is None:
            allowed = self._unknown_policy == "allow"
            decision = ArbitrationDecision(
                allowed=allowed,
                owner="UNKNOWN",
                reason=(
                    "unknown window — "
                    + ("relaxed policy allows" if allowed else "denied by default")
                ),
                tool=tool,
            )
        elif record.input_owner == InputOwner.USER:
            decision = ArbitrationDecision(
                allowed=False,
                owner=InputOwner.USER,
                reason=(
                    f"human-owned window {record.window_id} — "
                    "NEXUS input denied (Spec §62)"
                ),
                window_id=record.window_id,
                tool=tool,
            )
        elif record.input_owner == InputOwner.SHARED:
            decision = ArbitrationDecision(
                allowed=True,
                owner=InputOwner.SHARED,
                reason=(
                    f"shared window {record.window_id} — allowed with coordination"
                ),
                window_id=record.window_id,
                coordinated=True,
                tool=tool,
            )
        else:
            decision = ArbitrationDecision(
                allowed=True,
                owner=InputOwner.NEXUS,
                reason=f"NEXUS-owned window {record.window_id} — allowed",
                window_id=record.window_id,
                tool=tool,
            )
        self._log.append(decision)
        if len(self._log) > 256:
            del self._log[:128]
        if not decision.allowed:
            logger.info("arbitration veto: %s", decision.reason)
        return decision

    # ------------------------------------------------------------- hook

    def as_hook(self):  # noqa: ANN201 — the HarnessHooks Handler type
        """A Phase-6 ``pre_tool_call`` handler (veto-capable).

        Only input-bearing tools are arbitrated; everything else
        passes untouched (``None`` → no opinion, the loop continues).
        The target window comes from the ``hwnd`` argument when
        present, else from ``x``/``y`` coordinates (mouse), else the
        call is not window-targeted and passes.
        """

        def handler(context: HookContext) -> bool | None:
            if context.tool not in INPUT_TOOLS:
                return None
            arguments = dict(context.arguments)
            hwnd = arguments.get("hwnd")
            point = None
            if not isinstance(hwnd, int) or isinstance(hwnd, bool) or hwnd < 1:
                hwnd = None
                x, y = arguments.get("x"), arguments.get("y")
                if (
                    isinstance(x, int) and not isinstance(x, bool)
                    and isinstance(y, int) and not isinstance(y, bool)
                ):
                    point = (x, y)
            if hwnd is None and point is None:
                return None
            decision = self.request(hwnd=hwnd, point=point, tool=context.tool)
            return decision.allowed

        handler.__name__ = "nexus_input_arbitration"
        return handler

    # -------------------------------------------------------------- log

    def log(self) -> tuple[ArbitrationDecision, ...]:
        return tuple(self._log)


__all__ = [
    "INPUT_TOOLS",
    "ArbitrationDecision",
    "InputArbitrator",
]
