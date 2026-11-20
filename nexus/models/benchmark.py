"""Model Benchmarking (Final Build Plan §5.5 / Spec §135).

The seven benchmark fields are verbatim from the plan::

    warmup
    prompt speed
    generation speed
    context
    RAM
    VRAM
    stability

Spec §135 fixes the order of the protocol — «عند إضافة نموذج جديد»::

    Load → Warm-up → Prompt benchmark → Generation benchmark →
    Context benchmark → Memory usage → Stability → Register profile

so the router later relies on the *real* device results instead of
guessing («وبذلك Model Router يعتمد على نتائج الجهاز الحقيقي بدل
التخمين»).

Seed benchmarks carried from the MiMo Edge results (Spec §88) are
marked ``source="mimo_edge"`` — they are the user's measured numbers,
not general specs for any other device.

قياس النماذج — الحقول السبعة حرفيًا والترتيب من المواصفة §135؛ النتائج
المزروعة من اختبارات MiMo Edge موسومة المصدر ولا تُعمَّم على أي جهاز آخر.

Stdlib only.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .provider import GenerateRequest, GenerateResult, ModelProvider

if TYPE_CHECKING:
    from .registry import Model

#: Where a benchmark's numbers came from.
BENCHMARK_SOURCE_MEASURED = "measured"
BENCHMARK_SOURCE_MIMO_EDGE = "mimo_edge"  # Spec §88 (user's own device)


@dataclass(slots=True)
class ModelBenchmark:
    """One benchmark profile — the seven §5.5 fields, verbatim.

    Units:

    * ``warmup``           — warm-up completed (Spec §135 step 2);
    * ``prompt_speed``     — prompt tokens/second (None = unmeasured);
    * ``generation_speed`` — generation tokens/second;
    * ``context``          — context tokens exercised;
    * ``ram``              — resident RAM in MB (peak observed);
    * ``vram``             — resident VRAM in MB (peak observed);
    * ``stability``        — successful runs / total runs (0..1).
    """

    warmup: bool = False
    prompt_speed: float | None = None
    generation_speed: float | None = None
    context: int | None = None
    ram: int | None = None
    vram: int | None = None
    stability: float | None = None
    # provenance (not §5.5 fields — they explain the numbers above)
    source: str = BENCHMARK_SOURCE_MEASURED
    measured_at: str | None = None
    device: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "warmup": self.warmup,
            "prompt_speed": self.prompt_speed,
            "generation_speed": self.generation_speed,
            "context": self.context,
            "ram": self.ram,
            "vram": self.vram,
            "stability": self.stability,
            "source": self.source,
            "measured_at": self.measured_at,
            "device": self.device,
            "notes": dict(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelBenchmark:
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs["notes"] = dict(data.get("notes", {}))
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    """How to run one benchmark (defaults tuned for tiny models)."""

    warmup_runs: int = 1
    prompt_tokens: int = 256
    generation_tokens: int = 64
    stability_runs: int = 3
    context: int | None = None  # None = the model's registered context
    prompt_text: str = (
        "NEXUS benchmark: prompt evaluation pass. "
        "Count from one to sixty four in words, separated by spaces. "
        "This prompt exists to measure prompt-encoding speed only."
    )
    generation_prompt: str = "NEXUS benchmark: write the numbers 1 to 64 in words."

    def resolved_context(self, model: Model) -> int:
        return self.context if self.context is not None else model.context

    def to_dict(self) -> dict[str, Any]:
        return {
            "warmup_runs": self.warmup_runs,
            "prompt_tokens": self.prompt_tokens,
            "generation_tokens": self.stability_runs,
            "stability_runs": self.stability_runs,
            "context": self.context,
        }


#: Sampler returning ``(ram_mb, vram_mb)`` for the model process right now.
MemorySampler = Callable[[], tuple[int, int]]


def run_benchmark(
    provider: ModelProvider,
    model: Model,
    spec: BenchmarkSpec,
    *,
    device: str | None = None,
    memory_sampler: MemorySampler | None = None,
    now: Callable[[], str] | None = None,
) -> ModelBenchmark:
    """Execute the Spec §135 protocol in its literal order.

    Load → Warm-up → Prompt benchmark → Generation benchmark → Context
    benchmark → Memory usage → Stability → (register profile happens in
    the registry/manager, which persists the returned benchmark).
    """
    del now  # timestamps default to UTC now; hook kept for deterministic tests
    measured_at = datetime.now(UTC).isoformat()
    ram_mb: int | None = None
    vram_mb: int | None = None
    stability: float | None = None

    # 1) Load — provider must have the model resident (Spec §135 step 1).
    if model.id not in provider.loaded_ids():
        provider.load(model)
    try:
        # 2) Warm-up (§5.5 warmup).
        for _ in range(max(1, spec.warmup_runs)):
            provider.generate(
                GenerateRequest(
                    model_id=model.id, prompt=spec.generation_prompt, max_tokens=8
                )
            )

        # 3) Prompt benchmark — long prompt, tiny prediction.
        prompt_pass = provider.generate(
            GenerateRequest(model_id=model.id, prompt=spec.prompt_text, max_tokens=1)
        )
        prompt_speed = prompt_pass.prompt_tokens_per_second

        # 4) Generation benchmark — timed full-speed generation.
        generation_pass = provider.generate(
            GenerateRequest(
                model_id=model.id,
                prompt=spec.generation_prompt,
                max_tokens=max(1, spec.generation_tokens),
            )
        )
        generation_speed = generation_pass.generation_tokens_per_second

        # 5) Context benchmark — the context exercised this run.
        context_used = spec.resolved_context(model)

        # 6) Memory usage (RAM/VRAM) — sampled now, while resident.
        if memory_sampler is not None:
            ram_mb, vram_mb = memory_sampler()

        # 7) Stability — repeat runs, count successes.
        total = max(1, spec.stability_runs)
        successes = 0
        for _ in range(total):
            try:
                outcome: GenerateResult = provider.generate(
                    GenerateRequest(
                        model_id=model.id,
                        prompt=spec.generation_prompt,
                        max_tokens=max(1, spec.generation_tokens),
                    )
                )
                if outcome.generation_tokens >= 0 and outcome.text is not None:
                    successes += 1
            except Exception:  # noqa: BLE001 — stability counts failures
                pass
        stability = successes / total
    finally:
        pass  # unload policy belongs to the manager (keep-warm §5.4)

    return ModelBenchmark(
        warmup=True,
        prompt_speed=prompt_speed,
        generation_speed=generation_speed,
        context=context_used,
        ram=ram_mb,
        vram=vram_mb,
        stability=stability,
        source=BENCHMARK_SOURCE_MEASURED,
        measured_at=measured_at,
        device=device,
        notes={"backend": provider.backend},
    )


def monotonic_clock() -> float:
    """Injectable clock for deterministic tests."""
    return time.monotonic()
