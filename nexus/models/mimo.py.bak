"""MiMo Edge Profile (Final Build Plan §5.6 / Spec §88).

The **first Model Pool** — the five models from the user's own MiMo
Edge tests, seeded with *their measured results* as the initial
benchmark baseline::

    Qwen2.5-Coder-1.5B   ~9.57 tok/s @ ctx 8192
    LFM2.5-1.2B          ~7.54 tok/s @ ctx 8192
    Qwen3-0.6B (KV-Q4)   ~11.66 tok/s (measured)
    DS-Coder-1.3B (GPU)  ~29.14 tok/s (measured)
    Yi-Coder-1.5B        — awaiting on-device benchmark

Spec §88 is explicit: these numbers are **the user's test-environment
results**, not general specs for any other device. Seeded benchmarks
carry ``source="mimo_edge"`` and the device tag below.

Plan §5.6 is equally explicit — «لا تجعل هذه القائمة ثابتة»:

> the list is not fixed; it is only the first Model Pool.

So seeding is idempotent, never blocks ``unregister``, and never
overrides a newer on-device benchmark.

Device learnings from §88 kept as benchmark notes:

* KV-Q4 cut KV memory ~4× with a generation-speed gain;
* Flash Attention was **not** suitable for the AVX-only host;
* the tested ngram/router flags were unsupported in that build.

بروفايل MiMo Edge — أول مجموعة نماذج بنتائج جهاز المستخدم نفسه
(مواصفة §88)؛ القائمة ليست نهائية والزرع idempotent.

Stdlib only.
"""

from __future__ import annotations

from .benchmark import BENCHMARK_SOURCE_MIMO_EDGE, ModelBenchmark
from .provider import ModelCapability
from .registry import (
    BACKEND_LLAMA_CPP,
    FORMAT_GGUF,
    Model,
    ModelRegistry,
    ModelStatus,
)

#: Device tag for the MiMo Edge measurements (Spec §88 — user's own host).
MIMO_EDGE_DEVICE = "mimo-edge/user-device"

#: tok/s values exactly as reported in Spec §88 (approx, ctx=8192).
MIMO_QWEN25_CODER_15B_TPS = 9.57
MIMO_LFM25_12B_TPS = 7.54
MIMO_QWEN3_06B_TPS = 11.66
MIMO_DS_CODER_13B_TPS = 29.14


def _seed_benchmark(generation_speed: float | None, **notes: object) -> ModelBenchmark:
    return ModelBenchmark(
        warmup=True,
        prompt_speed=None,  # §88 reported generation speed only
        generation_speed=generation_speed,
        context=8192,
        ram=None,  # not reported — filled by on-device benchmark (§5.5)
        vram=None,
        stability=None,
        source=BENCHMARK_SOURCE_MIMO_EDGE,
        measured_at=None,
        device=MIMO_EDGE_DEVICE,
        notes=dict(notes),
    )


def mimo_edge_pool() -> tuple[Model, ...]:
    """The five §5.6 models with the §88 measured baselines.

    ``size``/``ram``/``vram`` are documented **estimates** for tiny
    Q4-class models pending the on-device §5.5 benchmark; speeds are
    the user's measured results.
    """
    return (
        Model(
            id="qwen2.5-coder-1.5b",
            name="Qwen2.5-Coder-1.5B",
            format=FORMAT_GGUF,
            backend=BACKEND_LLAMA_CPP,
            size=1_100_000_000,
            context=8192,
            capabilities=(ModelCapability.CODING, ModelCapability.CHAT),
            ram=2048,
            vram=0,
            language=("en", "zh"),
            benchmark=_seed_benchmark(
                MIMO_QWEN25_CODER_15B_TPS,
                backend=BACKEND_LLAMA_CPP,
            ),
            status=ModelStatus.BENCHMARKED,
        ),
        Model(
            id="lfm2.5-1.2b",
            name="LFM2.5-1.2B",
            format=FORMAT_GGUF,
            backend=BACKEND_LLAMA_CPP,
            size=900_000_000,
            context=8192,
            capabilities=(ModelCapability.CHAT,),
            ram=1792,
            vram=0,
            language=("en", "ar"),
            benchmark=_seed_benchmark(
                MIMO_LFM25_12B_TPS,
                backend=BACKEND_LLAMA_CPP,
            ),
            status=ModelStatus.BENCHMARKED,
        ),
        Model(
            id="qwen3-0.6b",
            name="Qwen3-0.6B",
            format=FORMAT_GGUF,
            backend=BACKEND_LLAMA_CPP,
            size=500_000_000,
            context=8192,
            capabilities=(ModelCapability.CHAT,),
            ram=1024,
            vram=0,
            language=("en", "zh"),
            benchmark=_seed_benchmark(
                MIMO_QWEN3_06B_TPS,
                backend=BACKEND_LLAMA_CPP,
                kv_quant="q4_0",  # §88: KV-Q4 ≈ 4× KV-memory reduction
                kv_memory_reduction="~4x",
            ),
            status=ModelStatus.BENCHMARKED,
        ),
        Model(
            id="ds-coder-1.3b",
            name="DS-Coder-1.3B",
            format=FORMAT_GGUF,
            backend=BACKEND_LLAMA_CPP,
            size=900_000_000,
            context=8192,
            capabilities=(ModelCapability.CODING,),
            ram=1024,
            vram=2048,
            language=("en", "zh"),
            benchmark=_seed_benchmark(
                MIMO_DS_CODER_13B_TPS,
                backend=BACKEND_LLAMA_CPP,
                gpu_offload=True,  # §88: measured with GPU offload
            ),
            status=ModelStatus.BENCHMARKED,
        ),
        Model(
            id="yi-coder-1.5b",
            name="Yi-Coder-1.5B",
            format=FORMAT_GGUF,
            backend=BACKEND_LLAMA_CPP,
            size=1_000_000_000,
            context=8192,
            capabilities=(ModelCapability.CODING, ModelCapability.CHAT),
            ram=2048,
            vram=0,
            language=("en", "zh"),
            benchmark=None,  # §88 listed no result — awaiting on-device run
            status=ModelStatus.REGISTERED,
        ),
    )


def seed_mimo_edge_pool(registry: ModelRegistry) -> tuple[str, ...]:
    """Register the §5.6 pool idempotently; returns the ids seeded now.

    Existing records and newer benchmarks are never overwritten
    (Plan §5.6: the pool is a starting point, not a fixed list).
    """
    seeded: list[str] = []
    for model in mimo_edge_pool():
        if registry.find(model.id) is None:
            registry.register(model)
            seeded.append(model.id)
    return tuple(seeded)


__all__ = [
    "MIMO_DS_CODER_13B_TPS",
    "MIMO_EDGE_DEVICE",
    "MIMO_LFM25_12B_TPS",
    "MIMO_QWEN25_CODER_15B_TPS",
    "MIMO_QWEN3_06B_TPS",
    "mimo_edge_pool",
    "seed_mimo_edge_pool",
]
