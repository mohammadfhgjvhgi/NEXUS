"""Window Manager + Human Parallelism (Final Build Plan §10).

* :mod:`nexus.windows.registry`    — §10.1 the nine-field Window
                                      Registry (and the first real
                                      publisher of the canonical
                                      window.opened/closed events)
* :mod:`nexus.windows.ownership`   — §10.2 USER / NEXUS / SHARED
* :mod:`nexus.windows.arbitration` — §10.3 per-window input verdicts
                                      + the ``pre_tool_call`` veto
* :mod:`nexus.windows.monitors`    — §10.4 the monitor topology and
                                      window placement
* :mod:`nexus.windows.overlay`     — §10.5 the transparent overlay
                                      (NEXUS is working · Pause ·
                                      Resume — pure ctypes)
* :mod:`nexus.windows.manager`     — the composer over the §9.1
                                      Computer API

The phase's goal, in the operator's words: you use your machine
while NEXUS works somewhere else on it. Ownership is per window —
never per mouse-move (Spec §62) — and every real effect still
passes the §8.2 router: the manager is policy and bookkeeping.

مدير النوافذ والتوازي مع الإنسان — الملكية لكل نافذة،
والتأثيرات خلف الموجّه نفسه.

Stdlib only.
"""

from __future__ import annotations

from .arbitration import (
    INPUT_TOOLS,
    ArbitrationDecision,
    InputArbitrator,
)
from .manager import WindowManager, build_window_manager
from .monitors import MonitorLayout, MonitorRecord
from .overlay import (
    STATUS_PAUSED,
    STATUS_WORKING,
    NativeOverlay,
    OverlayController,
    OverlayError,
    OverlayState,
    build_overlay,
)
from .ownership import (
    DEMO_RULES,
    OWNERS,
    InputOwner,
    OwnershipPolicy,
    OwnershipRule,
    parse_rules,
)
from .registry import (
    INPUT_OWNERS,
    VISIBILITIES,
    IngestReport,
    WindowRecord,
    WindowRegistry,
    window_id_for,
)

#: The §10 sections this package implements, verbatim.
WINDOWS_SECTIONS: tuple[str, ...] = (
    "registry",      # §10.1
    "ownership",     # §10.2
    "arbitration",   # §10.3
    "monitors",      # §10.4
    "overlay",       # §10.5
)

__all__ = [
    "WINDOWS_SECTIONS",
    # §10.1
    "IngestReport",
    "INPUT_OWNERS",
    "VISIBILITIES",
    "WindowRecord",
    "WindowRegistry",
    "window_id_for",
    # §10.2
    "DEMO_RULES",
    "InputOwner",
    "OWNERS",
    "OwnershipPolicy",
    "OwnershipRule",
    "parse_rules",
    # §10.3
    "INPUT_TOOLS",
    "ArbitrationDecision",
    "InputArbitrator",
    # §10.4
    "MonitorLayout",
    "MonitorRecord",
    # §10.5
    "NativeOverlay",
    "OverlayController",
    "OverlayError",
    "OverlayState",
    "STATUS_PAUSED",
    "STATUS_WORKING",
    "build_overlay",
    # façade
    "WindowManager",
    "build_window_manager",
]
