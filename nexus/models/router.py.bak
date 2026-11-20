"""Model Router (Final Build Plan §5.7 / Spec §136, §178, §87).

Input, verbatim from the plan::

    Task type
    Complexity
    Required capability
    RAM
    VRAM
    Current workload

Output, verbatim::

    selected model id

The score is the Spec §178 sum::

    Task fit + Capabilities + RAM + VRAM + Latency + Context +
    Observed reliability

with the Spec §87 rule applied first — capability requirement and
RAM/VRAM/current-load act as *filters*, then the score ranks what
survived. When nothing qualifies the router returns ``None`` with a
reason (e.g. a vision request with no vision model in the pool) —
inventing a winner would defeat the whole point.

Task-type → capability mapping follows the Spec §136 examples::

    Delete file        → fast tiny (quick_action)
    General chat       → small general (chat)
    Coding             → coder
    Large project      → long-context candidate (long_context)
    Image/screen       → vision
    Speech             → speech model

الموجّه — المدخلات والمخرجات حرفيًا من الخطة؛ المكوّنات من المواصفة §178،
والفلاتر أولًا (قاعدة §87).

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .provider import ModelCapability
from .registry import Model, ModelStatus

#: Task types with a Spec §136 mapping (others may be passed freely).
TASK_QUICK_ACTION = "quick_action"          # «Delete file → Fast tiny»
TASK_CHAT = "chat"                          # «General chat → Small general»
TASK_CODING = "coding"                      # «Coding → Coder»
TASK_LONG_CONTEXT = "long_context"          # «Large project analysis»
TASK_VISION = "vision"                      # «Image/screen → Vision»
TASK_SPEECH = "speech"                      # «Speech → Speech model»
TASK_EMBEDDING = "embedding"

#: Spec §136 task type → the capability a candidate must serve.
#: ``long_context`` is deliberately ``None`` — it is a quantitative
#: need (context tokens, enforced via :data:`TASK_MIN_CONTEXT`), not a
#: qualitative capability: any pool model with enough context is a
#: «long-context candidate».
TASK_CAPABILITY_MAP: dict[str, str | None] = {
    TASK_QUICK_ACTION: None,  # any capable model; smallness wins
    TASK_CHAT: ModelCapability.CHAT,
    TASK_CODING: ModelCapability.CODING,
    TASK_LONG_CONTEXT: None,
    TASK_VISION: ModelCapability.VISION,
    TASK_SPEECH: ModelCapability.SPEECH,
    TASK_EMBEDDING: ModelCapability.EMBEDDINGS,
}

#: Minimum context tokens per task type (Spec §136 long-context rule).
TASK_MIN_CONTEXT: dict[str, int] = {
    TASK_QUICK_ACTION: 512,
    TASK_CHAT: 2048,
    TASK_CODING: 4096,
    TASK_LONG_CONTEXT: 8192,
    TASK_VISION: 2048,
    TASK_SPEECH: 2048,
    TASK_EMBEDDING: 1024,
}

#: Statuses that may not be selected (they failed or vanished).
BLOCKED_STATUSES = (ModelStatus.ERROR, ModelStatus.UNAVAILABLE)


@dataclass(slots=True)
class RoutingRequest:
    """The §5.7 inputs, verbatim.

    ``ram_mb``/``vram_mb`` are the *available* budgets right now (the
    manager passes the ResourceManager's); ``current_workload`` is a
    0..1 saturation measure of loaded models / in-flight work.
    """

    task_type: str = TASK_CHAT
    complexity: float = 0.5  # 0..1 (plan: «Complexity»)
    required_capability: str | None = None
    ram_mb: int | None = None
    vram_mb: int | None = None
    current_workload: float = 0.0
    #: context tokens the task needs (derived from task type if absent)
    context_tokens: int | None = None

    def resolved_capability(self) -> str | None:
        if self.required_capability is not None:
            return self.required_capability
        return TASK_CAPABILITY_MAP.get(self.task_type)

    def resolved_context(self) -> int:
        if self.context_tokens is not None:
            return self.context_tokens
        return TASK_MIN_CONTEXT.get(self.task_type, 2048)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "complexity": self.complexity,
            "required_capability": self.required_capability,
            "ram_mb": self.ram_mb,
            "vram_mb": self.vram_mb,
            "current_workload": self.current_workload,
            "context_tokens": self.context_tokens,
        }


@dataclass(slots=True)
class ModelScore:
    """One candidate's §178 component breakdown (audit-ready)."""

    model_id: str
    total: float
    task_fit: float
    capabilities: float
    ram: float
    vram: float
    latency: float
    context: float
    reliability: float
    warm_bonus: float = 0.0

    def to_dict(self) -> dict[str, float | str]:
        return {
            "model_id": self.model_id,
            "total": round(self.total, 4),
            "task_fit": round(self.task_fit, 4),
            "capabilities": round(self.capabilities, 4),
            "ram": round(self.ram, 4),
            "vram": round(self.vram, 4),
            "latency": round(self.latency, 4),
            "context": round(self.context, 4),
            "reliability": round(self.reliability, 4),
            "warm_bonus": round(self.warm_bonus, 4),
        }


@dataclass(slots=True)
class RoutingDecision:
    """The §5.7 output — ``selected_model_id`` plus the audit trail."""

    selected_model_id: str | None
    reason: str
    request: RoutingRequest
    scores: tuple[ModelScore, ...] = field(default_factory=tuple)
    candidates_considered: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_model_id": self.selected_model_id,
            "reason": self.reason,
            "request": self.request.to_dict(),
            "candidates_considered": self.candidates_considered,
            "scores": [s.to_dict() for s in self.scores],
        }


#: Spec §178 components → weights (documented, deterministic).
SCORE_WEIGHTS: dict[str, float] = {
    "task_fit": 0.25,
    "capabilities": 0.05,
    "ram": 0.15,
    "vram": 0.15,
    "latency": 0.15,
    "context": 0.15,
    "reliability": 0.10,
}

#: Unknown-evidence defaults. Latency unknown sits *below* every
#: measured model of the §88 pool (Spec §135: the router relies on
#: real device results, not guesses — an unbenchmarked model must
#: not outrank a measured one); reliability unknown stays neutral.
NEUTRAL = 0.5
NEUTRAL_LATENCY = 0.35


class ModelRouter:
    """Selects one model id for one routing request (Plan §5.7)."""

    def __init__(self, *, warm_ids: frozenset[str] = frozenset()) -> None:
        self._warm_ids = set(warm_ids)

    # ------------------------------------------------------------- helpers

    def set_warm_ids(self, model_ids: frozenset[str]) -> None:
        """Tell the router which models are resident (Spec §87 current
        load: a warm model avoids reload cost)."""
        self._warm_ids = set(model_ids)

    def warm_ids(self) -> frozenset[str]:
        return frozenset(self._warm_ids)

    # ------------------------------------------------------------- routing

    def eligible(self, model: Model, request: RoutingRequest) -> str | None:
        """Spec §87 filters; returns a rejection reason or ``None``."""
        if model.status in BLOCKED_STATUSES:
            return f"status={model.status}"
        capability = request.resolved_capability()
        if capability is not None and not model.has_capability(capability):
            return f"missing capability {capability!r}"
        if not model.fits(ram_mb=request.ram_mb, vram_mb=request.vram_mb):
            return "ram/vram over budget"
        if model.context < request.resolved_context():
            return f"context {model.context} < {request.resolved_context()}"
        return None

    def score(self, model: Model, request: RoutingRequest) -> ModelScore:
        """The §178 component scores for one eligible model.

        Complexity (§5.7 input) blends the weights: as it rises the
        score leans toward **depth** (context coverage, capability
        richness) and away from **cheapness** (latency, RAM headroom).
        """
        complexity = max(0.0, min(1.0, request.complexity))
        w = {key: value for key, value in SCORE_WEIGHTS.items()}
        w["latency"] *= 1.0 - 0.5 * complexity
        w["ram"] *= 1.0 - 0.5 * complexity
        w["context"] *= 1.0 + complexity
        w["capabilities"] *= 1.0 + 3.0 * complexity

        # Task fit — capability alignment with the task.
        capability = request.resolved_capability()
        if capability is None:
            task_fit = 0.6  # quick actions: any capable model serves
            if model.has_capability(ModelCapability.CHAT):
                task_fit = 0.8
        elif model.has_capability(capability):
            task_fit = 1.0
        else:
            task_fit = 0.0

        # Capabilities — versatility (more served capabilities).
        capabilities = min(1.0, len(model.capabilities) / 4.0)

        # RAM/VRAM — headroom left after loading (smaller = better).
        ram = self._headroom_score(model.ram, request.ram_mb)
        vram = self._headroom_score(model.vram, request.vram_mb, default=0.8)

        # Latency — observed generation speed (tok/s); sqrt curve
        # keeps the tiny-local regime honest (§88 pool: 7.5–29 tps).
        latency = NEUTRAL_LATENCY
        speed = model.benchmark.generation_speed if model.benchmark else None
        if speed is not None:
            latency = _speed_score(speed)

        # Context — comfortably covering the need without waste.
        need = request.resolved_context()
        context = _context_score(model.context, need)

        # Observed reliability — benchmark stability when measured.
        reliability = NEUTRAL
        stability = model.benchmark.stability if model.benchmark else None
        if stability is not None:
            reliability = max(0.0, min(1.0, stability))

        # Current workload (§87 current load): under pressure, warm
        # models and small footprints matter more.
        warm_bonus = 0.0
        if model.id in self._warm_ids:
            warm_bonus = 0.15 * (0.5 + 0.5 * request.current_workload)

        total = (
            w["task_fit"] * task_fit
            + w["capabilities"] * capabilities
            + w["ram"] * ram
            + w["vram"] * vram
            + w["latency"] * latency
            + w["context"] * context
            + w["reliability"] * reliability
            + warm_bonus
        )
        return ModelScore(
            model_id=model.id,
            total=total,
            task_fit=task_fit,
            capabilities=capabilities,
            ram=ram,
            vram=vram,
            latency=latency,
            context=context,
            reliability=reliability,
            warm_bonus=warm_bonus,
        )

    def route(
        self, models: tuple[Model, ...], request: RoutingRequest
    ) -> RoutingDecision:
        """Filter (§87) → score (§178) → pick; ``None`` when nothing
        qualifies, with the honest reason."""
        eligible: list[tuple[Model, ModelScore]] = []
        rejected: list[str] = []
        for model in models:
            reason = self.eligible(model, request)
            if reason is not None:
                rejected.append(f"{model.id}: {reason}")
                continue
            eligible.append((model, self.score(model, request)))
        if not eligible:
            detail = "; ".join(rejected[:6]) if rejected else "no models registered"
            return RoutingDecision(
                selected_model_id=None,
                reason=f"no eligible model ({detail})",
                request=request,
                candidates_considered=len(models),
            )
        eligible.sort(key=lambda pair: pair[1].total, reverse=True)
        winner, best = eligible[0]
        return RoutingDecision(
            selected_model_id=winner.id,
            reason=(
                f"best §178 score {best.total:.3f} of "
                f"{len(eligible)} eligible candidates"
            ),
            request=request,
            scores=tuple(score for _, score in eligible),
            candidates_considered=len(models),
        )

    # ------------------------------------------------------------- private

    @staticmethod
    def _headroom_score(
        need_mb: int, available_mb: int | None, *, default: float = 0.5
    ) -> float:
        """0 when need==available (no headroom), →1 as need shrinks."""
        if need_mb <= 0:
            return 1.0
        if available_mb is None or available_mb <= 0:
            return default
        ratio = need_mb / float(available_mb)
        if ratio >= 1.0:
            return 0.0
        return max(0.0, 1.0 - ratio)


def _speed_score(tok_per_s: float) -> float:
    """Map tok/s to 0..1 with a sqrt curve — 2 tok/s → 0, 30 tok/s →
    saturation (the tiny-model regime of the MiMo Edge pool, §88:
    7.5–29 tok/s). A measured 7.5 tps (≈0.45) still beats the unknown
    default 0.35, so real results always outrank guesses."""
    if tok_per_s <= 2.0:
        return 0.0
    scaled = ((tok_per_s - 2.0) / 28.0) ** 0.5
    return max(0.0, min(1.0, scaled))


def _context_score(model_context: int, needed: int) -> float:
    """1.0 at exactly covering the need; decays for oversized or short."""
    if needed <= 0:
        return 1.0
    if model_context < needed:
        return 0.0
    ratio = model_context / float(needed)
    if ratio <= 1.25:
        return 1.0
    if ratio >= 8.0:
        return 0.4  # oversized context wastes KV memory (§88 KV-Q4 note)
    # linear decay 1.25..8.0
    return 1.0 - 0.6 * (ratio - 1.25) / (8.0 - 1.25)


__all__ = [
    "BLOCKED_STATUSES",
    "ModelRouter",
    "ModelScore",
    "NEUTRAL",
    "NEUTRAL_LATENCY",
    "RoutingDecision",
    "RoutingRequest",
    "SCORE_WEIGHTS",
    "TASK_CAPABILITY_MAP",
    "TASK_CHAT",
    "TASK_CODING",
    "TASK_EMBEDDING",
    "TASK_LONG_CONTEXT",
    "TASK_MIN_CONTEXT",
    "TASK_QUICK_ACTION",
    "TASK_SPEECH",
    "TASK_VISION",
]
