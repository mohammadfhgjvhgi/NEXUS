"""Resource Policies (Final Build Plan §4.5 / Spec §92).

The plan's three verbatim mappings:

    RAM pressure  → reduce concurrency
    VRAM pressure → unload model / switch
    CPU pressure  → reduce background work

…run on top of the **Spec §92 degradation ladder**, verbatim:

    Reduce concurrency
    → Unload idle model
    → Switch smaller model
    → Reduce unnecessary context
    → Continue

The principle (both documents, verbatim in intent):

> نخفض السرعة قبل أن نخسر المهمة.
> البطء أفضل من ضياع المهمة.
> Slow down before losing the task.

The engine only *recommends* — degradation is data, and the ladder
always ends at **Continue**: NEXUS slows down, it never abandons the
task. There is deliberately no "abort" action.

سياسات الموارد — تُحوّل الضغط إلى سلّم تدهور مرتّب ينتهي دائمًا بالمتابعة.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from .profile import HardwareProfile  # noqa: F401 — re-export convenience

# ---------------------------------------------------------- pressure model


class PressureLevel(IntEnum):
    """Ordered pressure levels (NONE < LOW < MEDIUM < HIGH < CRITICAL)."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def label(self) -> str:
        return self.name.lower()


#: Ratio thresholds — none <0.70 · low ≥0.70 · medium ≥0.85 · high
#: ≥0.95 · critical >1.00 (over capacity).
THRESHOLD_LOW = 0.70
THRESHOLD_MEDIUM = 0.85
THRESHOLD_HIGH = 0.95
THRESHOLD_CRITICAL = 1.0


def level_for_ratio(ratio: float | None) -> PressureLevel:
    """Threshold map for a demand/capacity ratio."""
    if ratio is None:
        return PressureLevel.NONE
    if ratio > THRESHOLD_CRITICAL:
        return PressureLevel.CRITICAL
    if ratio >= THRESHOLD_HIGH:
        return PressureLevel.HIGH
    if ratio >= THRESHOLD_MEDIUM:
        return PressureLevel.MEDIUM
    if ratio >= THRESHOLD_LOW:
        return PressureLevel.LOW
    return PressureLevel.NONE


@dataclass(frozen=True, slots=True)
class PressureReading:
    """One resource's pressure: level + the ratio that produced it."""

    resource: str
    level: PressureLevel
    ratio: float | None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "level": self.level.label(),
            "ratio": round(self.ratio, 4) if self.ratio is not None else None,
            "detail": self.detail,
        }


# ---------------------------------------------------------------- actions


class ResourceAction:
    """The degradation actions (Spec §92 steps + the §4.5 CPU
    mapping). Values are stable strings."""

    REDUCE_CONCURRENCY = "reduce_concurrency"
    UNLOAD_MODEL = "unload_model"
    SWITCH_MODEL = "switch_model"
    REDUCE_CONTEXT = "reduce_context"
    REDUCE_BACKGROUND = "reduce_background"


#: Spec §92 ladder, verbatim order (Continue is the outcome, not an action).
DEGRADATION_LADDER: tuple[str, ...] = (
    ResourceAction.REDUCE_CONCURRENCY,
    ResourceAction.UNLOAD_MODEL,
    ResourceAction.SWITCH_MODEL,
    ResourceAction.REDUCE_CONTEXT,
)


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    """One policy recommendation: which action, why, how urgent."""

    action: str
    reason: str
    severity: PressureLevel
    source: str  # the pressure resource that produced it

    @property
    def ladder_position(self) -> int:
        """Spec §92 ladder position (unmapped actions sort last)."""
        try:
            return DEGRADATION_LADDER.index(self.action)
        except ValueError:
            return len(DEGRADATION_LADDER)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "severity": self.severity.label(),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ResourcePolicyDecision:
    """Outcome of one policy evaluation — audit-ready.

    ``always_continue`` is True by construction: the ladder's final
    step is Continue (Spec §92) — NEXUS degrades, it never abandons.
    """

    pressures: dict[str, PressureReading]
    actions: tuple[RecommendedAction, ...] = field(default_factory=tuple)
    degraded: bool = False
    summary: str = ""
    principle: str = "نخفض السرعة قبل أن نخسر المهمة — البطء أفضل من ضياع المهمة"

    @property
    def always_continue(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "degraded": self.degraded,
            "always_continue": self.always_continue,
            "summary": self.summary,
            "principle": self.principle,
            "pressures": {
                key: reading.to_dict()
                for key, reading in self.pressures.items()
            },
            "actions": [action.to_dict() for action in self.actions],
        }


class ResourcePolicyEngine:
    """Maps current pressures to ordered degradation actions (§4.5)."""

    def evaluate(
        self, pressures: Mapping[str, PressureReading]
    ) -> ResourcePolicyDecision:
        actions: list[RecommendedAction] = []
        summary_parts: list[str] = []

        for resource, reading in pressures.items():
            level = reading.level
            if level < PressureLevel.MEDIUM:
                continue

            # §4.5 verbatim: RAM pressure → reduce concurrency
            if resource == "ram":
                if level >= PressureLevel.MEDIUM:
                    actions.append(
                        RecommendedAction(
                            ResourceAction.REDUCE_CONCURRENCY,
                            f"RAM pressure {reading.detail}",
                            level,
                            "ram",
                        )
                    )
                if level >= PressureLevel.HIGH:
                    actions.append(
                        RecommendedAction(
                            ResourceAction.UNLOAD_MODEL,
                            f"RAM pressure {reading.detail} — free memory",
                            level,
                            "ram",
                        )
                    )

            # §4.5 verbatim: VRAM pressure → unload model / switch
            elif resource in ("vram", "gpu"):
                actions.append(
                    RecommendedAction(
                        ResourceAction.SWITCH_MODEL,
                        f"{resource.upper()} pressure {reading.detail}",
                        level,
                        resource,
                    )
                )
                if level >= PressureLevel.HIGH:
                    actions.append(
                        RecommendedAction(
                            ResourceAction.UNLOAD_MODEL,
                            f"{resource.upper()} pressure {reading.detail}",
                            level,
                            resource,
                        )
                    )

            # §4.5 verbatim: CPU pressure → reduce background work
            elif resource == "cpu":
                actions.append(
                    RecommendedAction(
                        ResourceAction.REDUCE_BACKGROUND,
                        f"CPU pressure {reading.detail}",
                        level,
                        "cpu",
                    )
                )

            # extension (documented): model memory & disk also degrade
            elif resource == "model_memory":
                actions.append(
                    RecommendedAction(
                        ResourceAction.UNLOAD_MODEL,
                        f"model-memory pressure {reading.detail}",
                        level,
                        "model_memory",
                    )
                )
            elif resource == "disk":
                if level >= PressureLevel.HIGH:
                    actions.append(
                        RecommendedAction(
                            ResourceAction.REDUCE_BACKGROUND,
                            f"disk pressure {reading.detail}",
                            level,
                            "disk",
                        )
                    )

            # ladder step 4 under critical memory conditions
            if (
                resource in ("ram", "vram", "model_memory")
                and level >= PressureLevel.CRITICAL
            ):
                actions.append(
                    RecommendedAction(
                        ResourceAction.REDUCE_CONTEXT,
                        f"{resource} critical — reduce unnecessary context",
                        level,
                        resource,
                    )
                )

            summary_parts.append(f"{resource}={reading.level.label()}")

        # Spec §92 order, then severity (worst first), then source —
        # one recommendation per distinct action (the strongest one).
        ordered: list[RecommendedAction] = []
        seen: set[str] = set()
        for action in sorted(
            actions,
            key=lambda item: (
                item.ladder_position,
                -int(item.severity),
                item.source,
            ),
        ):
            if action.action in seen:
                continue
            seen.add(action.action)
            ordered.append(action)
        degraded = bool(ordered)
        if degraded:
            summary = (
                "degrade and continue — "
                + ", ".join(summary_parts)
            )
        else:
            summary = "all resources comfortable — continue at full speed"
        return ResourcePolicyDecision(
            pressures=dict(pressures),
            actions=tuple(ordered),
            degraded=degraded,
            summary=summary,
        )
