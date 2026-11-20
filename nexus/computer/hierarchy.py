"""Computer Use Fallback Hierarchy (Final Build Plan §9.5, verbatim).

    Application API
        ↓
    Windows UI Automation
        ↓
    Browser DOM / Accessibility
        ↓
    Vision
        ↓
    Mouse/Keyboard

One coordinator, five layers, one contract per layer:

* :meth:`LayerProvider.available` — an honest probe (``(ok, reason)``),
  never a guess. Unregistered layers report unavailable, so the chain
  degrades to the next layer — that is the *point* of the hierarchy.
* :meth:`LayerProvider.act` — attempt the action; ``None`` means "this
  layer cannot serve this action" (recorded, fall through); a raised
  :class:`LayerError` means "tried and failed" (recorded, fall
  through); a :class:`LayerResult` means the layer succeeded and the
  chain stops there.

Every attempt lands in :class:`HierarchyTrace` — the caller (and the
agent) sees exactly which layer served the action and why the ones
above declined. No silent escalation, no silent swallow.

سلسلة التراجع — طبقة أنيقة أولًا، وبدائية أخيرًا، وكل محاولة
مُسجّلة بأمانة.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class HierarchyError(Exception):
    """Every layer declined or failed — the full trace rides along."""

    def __init__(self, message: str, trace: HierarchyTrace) -> None:
        super().__init__(message)
        self.trace = trace


class LayerError(Exception):
    """A layer tried and failed — fallback continues to the next layer."""


#: The §9.5 layer order, verbatim.
HIERARCHY_LAYERS: tuple[str, ...] = (
    "application_api",
    "uia",
    "dom_a11y",
    "vision",
    "input",
)


@dataclass(slots=True)
class ActionTarget:
    """One computer action request, layer-agnostic.

    ``action`` is one of: ``invoke`` · ``set_value`` · ``focus`` ·
    ``type`` · ``click`` · ``inspect``. Layers consume the fields they
    understand (``hwnd``, ``value``/``text``, ``point``) and ignore the
    rest.
    """

    action: str
    hwnd: int | None = None
    name: str | None = None
    value: str | None = None
    point: tuple[int, int] | None = None


@dataclass(slots=True)
class LayerResult:
    """A layer's success — what it did, in its own words."""

    layer: str
    summary: str
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LayerAttempt:
    """One recorded attempt (the chain's honest ledger)."""

    layer: str
    outcome: str  # "succeeded" | "unavailable" | "unsupported" | "failed"
    reason: str = ""


@dataclass(slots=True)
class HierarchyTrace:
    """The ordered ledger of one :meth:`HierarchyChain.act` run."""

    attempts: list[LayerAttempt] = field(default_factory=list)

    def record(self, layer: str, outcome: str, reason: str = "") -> None:
        self.attempts.append(
            LayerAttempt(layer=layer, outcome=outcome, reason=reason)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": [
                {
                    "layer": attempt.layer,
                    "outcome": attempt.outcome,
                    "reason": attempt.reason,
                }
                for attempt in self.attempts
            ]
        }


class LayerProvider:
    """The per-layer contract — subclass (or duck-type) per layer."""

    #: §9.5 layer name (must be one of :data:`HIERARCHY_LAYERS`).
    name: str = ""

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def act(self, target: ActionTarget) -> LayerResult | None:
        raise NotImplementedError


@dataclass(slots=True)
class _ProviderLayer:
    name: str
    probe: Callable[[], tuple[bool, str]]
    action: Callable[[ActionTarget], LayerResult | None]


class HierarchyChain:
    """The §9.5 coordinator — strict order, honest bookkeeping.

    Providers may be registered per layer; multiple providers for one
    layer are tried in registration order (the first success wins).
    A layer with no provider is *unavailable* by definition.
    """

    def __init__(self) -> None:
        self._providers: dict[str, list[LayerProvider]] = {
            layer: [] for layer in HIERARCHY_LAYERS
        }

    # -------------------------------------------------------- registry

    def register(self, provider: LayerProvider) -> None:
        if provider.name not in self._providers:
            raise HierarchyError(
                f"unknown §9.5 layer {provider.name!r} "
                f"(expected one of {list(HIERARCHY_LAYERS)})", HierarchyTrace()
            )
        self._providers[provider.name].append(provider)

    def layers(self) -> tuple[str, ...]:
        return HIERARCHY_LAYERS

    def describe(self) -> dict[str, Any]:
        report: dict[str, Any] = {}
        for layer in HIERARCHY_LAYERS:
            probes = [probe.available() for probe in self._providers[layer]]
            report[layer] = {
                "providers": len(probes),
                "available": any(ok for ok, _reason in probes),
                "reasons": [reason for _ok, reason in probes] or
                ["no provider registered"],
            }
        return report

    # ------------------------------------------------------------ act

    def act(self, target: ActionTarget) -> LayerResult:
        """Try the layers in §9.5 order; the first success wins."""
        trace = HierarchyTrace()
        for layer in HIERARCHY_LAYERS:
            providers = self._providers[layer]
            if not providers:
                trace.record(layer, "unavailable", "no provider registered")
                continue
            for provider in providers:
                ok, reason = provider.available()
                if not ok:
                    trace.record(layer, "unavailable", reason)
                    continue
                try:
                    result = provider.act(target)
                except LayerError as exc:
                    trace.record(layer, "failed", str(exc))
                    continue
                if result is None:
                    trace.record(
                        layer, "unsupported", "action not served by this layer"
                    )
                    continue
                trace.record(layer, "succeeded", result.summary)
                result.layer = layer
                return result
        raise HierarchyError(
            f"no §9.5 layer could {target.action!r} "
            f"({len(trace.attempts)} attempts recorded)", trace
        )
