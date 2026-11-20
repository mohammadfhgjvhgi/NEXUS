"""Simulated provider (Final Build Plan §5.1, §5.4, §5.5 support).

A deterministic, in-process :class:`ModelProvider` used by the exit
criteria harness and as a fallback backend when no inference runtime
is installed — the abstraction, registry, router, manager, benchmarks
and events can all be exercised without llama.cpp.

It follows the same seven-member contract as the llama.cpp adapter,
with configurable timing math (tokens ÷ speed → seconds) and a full
call log for auditing the §5.4 lifecycle and the §135 order.

مزوّد محاكاة حتمي — للتحقق من الواجهة والدورة والقياس بلا أي backend.

Stdlib only.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from .benchmark import BenchmarkSpec, ModelBenchmark, run_benchmark
from .provider import (
    GenerateRequest,
    GenerateResult,
    LoadInfo,
    ModelCapability,
    ModelNotLoadedError,
    ModelProvider,
    ProviderHealth,
    StreamChunk,
    UnsupportedModelError,
)
from .registry import Model

#: Deterministic tok/s used when a model carries no benchmark.
DEFAULT_SPEED_TPS = 12.0


class SimulatedProvider(ModelProvider):
    """Deterministic in-process provider (no subprocess, no network)."""

    backend = "simulated"

    def __init__(self, *, speed_tps: float | None = None) -> None:
        self._speed_tps = speed_tps
        self._loaded: dict[str, Model] = {}
        self.call_log: list[str] = []  # audit: the §5.4/§135 verb order

    # ------------------------------------------------------------- helpers

    def _speed(self, model: Model) -> float:
        if self._speed_tps is not None:
            return self._speed_tps
        benchmark = model.benchmark
        if benchmark and benchmark.generation_speed:
            return benchmark.generation_speed
        return DEFAULT_SPEED_TPS

    @staticmethod
    def _tokens(text: str) -> int:
        return max(1, len(text.split()))

    def _result(self, request: GenerateRequest, model: Model) -> GenerateResult:
        speed = self._speed(model)
        prompt_tokens = self._tokens(request.prompt)
        generation_tokens = max(1, request.max_tokens)
        text = (
            f"[{model.id}] simulated response "
            + " ".join(f"tok{i}" for i in range(generation_tokens))
        )
        return GenerateResult(
            model_id=model.id,
            backend=self.backend,
            text=text,
            prompt_tokens=prompt_tokens,
            generation_tokens=generation_tokens,
            prompt_seconds=prompt_tokens / max(speed, 0.001),
            generation_seconds=generation_tokens / max(speed, 0.001),
        )

    # ---------------------------------------------------------- §5.1 API

    def load(self, model: Model) -> LoadInfo:
        self.call_log.append(f"load:{model.id}")
        if model.format and model.format.upper() not in {"GGUF", "SIMULATED"}:
            raise UnsupportedModelError(
                f"simulated provider serves GGUF records, got {model.format!r}"
            )
        self._loaded[model.id] = model
        return LoadInfo(
            model_id=model.id, backend=self.backend, detail="in-process"
        )

    def unload(self, model_id: str) -> None:
        if model_id not in self._loaded:
            raise ModelNotLoadedError(f"model {model_id!r} is not loaded")
        self.call_log.append(f"unload:{model_id}")
        self._loaded.pop(model_id)

    def generate(self, request: GenerateRequest) -> GenerateResult:
        model = self._require(request.model_id)
        self.call_log.append(f"generate:{request.model_id}")
        return self._result(request, model)

    def stream(self, request: GenerateRequest) -> Iterator[StreamChunk]:
        model = self._require(request.model_id)
        self.call_log.append(f"stream:{request.model_id}")
        result = self._result(request, model)
        pieces = result.text.split(" ")
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            delta = piece if i == 0 else f" {piece}"
            yield StreamChunk(
                model_id=model.id,
                delta=delta,
                done=last,
                result=result if last else None,
            )

    def health(self, model_id: str) -> ProviderHealth:
        if model_id not in self._loaded:
            return ProviderHealth(
                model_id=model_id, ok=False, status="not_loaded",
                detail="simulated model is not loaded",
            )
        return ProviderHealth(
            model_id=model_id, ok=True, status="ok", detail="simulated"
        )

    def capabilities(self, model_id: str) -> tuple[str, ...]:
        model = self._loaded.get(model_id)
        return model.capabilities if model else (ModelCapability.CHAT,)

    def benchmark(self, model: Model, spec: BenchmarkSpec) -> ModelBenchmark:
        self.call_log.append(f"benchmark:{model.id}")
        started = time.monotonic()
        mark = run_benchmark(self, model, spec)
        # keep the audit log useful: the runner already exercised §135
        self.call_log.append(f"benchmark_done:{model.id}:{time.monotonic() - started:.3f}")
        return mark

    # ------------------------------------------------------------ concrete

    def loaded_ids(self) -> tuple[str, ...]:
        return tuple(self._loaded)

    def close(self) -> None:
        for model_id in list(self._loaded):
            self.call_log.append(f"close:{model_id}")
            self._loaded.pop(model_id)

    # -------------------------------------------------------------- private

    def _require(self, model_id: str) -> Model:
        model = self._loaded.get(model_id)
        if model is None:
            raise ModelNotLoadedError(
                f"model {model_id!r} is not loaded — call load() first (§5.4)"
            )
        return model


def provider_backend(provider: ModelProvider) -> str:
    """Return a provider's backend identity (audit helper)."""
    return str(getattr(provider, "backend", "unknown"))


__all__ = ["DEFAULT_SPEED_TPS", "SimulatedProvider", "provider_backend"]
