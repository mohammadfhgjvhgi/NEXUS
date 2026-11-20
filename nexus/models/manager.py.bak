"""Model Manager — Dynamic Loading (Final Build Plan §5.4 / Spec §87).

The §5.4 verbs, verbatim::

    select
    load
    run
    keep warm
    unload

«بحسب الموارد» — everything is resource-aware:

* ``select`` delegates to the §5.7 router with the ResourceManager's
  live RAM/VRAM budgets and the current workload;
* ``load`` *reserves* the model's RAM/VRAM in the ResourceManager
  **before** spawning anything (Spec §91: one task must never crash
  the machine); when the budget refuses, the manager first drops
  keep-warm idlers (Spec §92: «Unload idle model») and retries once;
* ``run`` is ``generate``/``stream`` against the provider, updating
  keep-warm liveness and translating failures into ``model.error``;
* ``keep warm`` — a TTL per loaded model; ``unload_idle`` expires the
  idlers, and ``apply_pressure`` reacts to the §92 degradation ladder
  (unload idle → unload LRU → prepare a switch to a smaller model);
* ``unload`` releases the provider runtime and the ResourceManager
  allocation together, in that order.

Events: only the four §2.2 model events — ``model.loading``,
``model.loaded``, ``model.unloaded``, ``model.error``. No new names
(the 28-event registry is authoritative and binding).

مدير النماذج — الأفعال الخمسة حرفيًا، وكلها وفق الموارد: الحجز قبل
التحميل، وإخلاء الخاملين عند الضغط، وسلّم التدهور §92 بلا abort.

Stdlib only.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..events import EventBus, EventName
from .benchmark import BenchmarkSpec, ModelBenchmark, run_benchmark
from .mimo import seed_mimo_edge_pool
from .provider import (
    GenerateRequest,
    GenerateResult,
    ModelProvider,
    ProviderError,
    ProviderHealth,
    StreamChunk,
)
from .registry import (
    REGISTRY_FILE,
    Model,
    ModelRegistry,
    ModelStatus,
)
from .router import ModelRouter, RoutingDecision, RoutingRequest

if TYPE_CHECKING:
    from ..resources import ResourceManager, ResourcePolicyDecision

logger = logging.getLogger("nexus.models")

#: Default keep-warm TTL (seconds) — matches ``models.keep_warm_seconds``.
DEFAULT_KEEP_WARM_SECONDS = 300


class ModelManagerError(Exception):
    """Model-manager misuse (unknown model, budget refusal…)."""


class LoadRefusedError(ModelManagerError):
    """The ResourceManager refused the allocation even after evicting
    idlers — per Spec §91/§92 the task slows down, it does not crash."""


@dataclass(slots=True)
class LoadedModel:
    """One resident model's bookkeeping (the §5.4 runtime state)."""

    model_id: str
    backend: str
    loaded_at: str
    ram_mb: int
    vram_mb: int
    last_used_monotonic: float
    generations: int = 0
    keep_warm_seconds: float = DEFAULT_KEEP_WARM_SECONDS
    endpoint: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "backend": self.backend,
            "loaded_at": self.loaded_at,
            "ram_mb": self.ram_mb,
            "vram_mb": self.vram_mb,
            "generations": self.generations,
            "keep_warm_seconds": self.keep_warm_seconds,
            "endpoint": self.endpoint,
        }


@dataclass(slots=True)
class ManagerEvent:
    """Audit row for the manager's own operations (not a bus event)."""

    verb: str  # select | load | run | keep_warm | unload | benchmark
    model_id: str
    detail: str = ""
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ModelManager:
    """Dynamic Loading per resources (Plan §5.4) — the NEXUS Model API's
    manager side. Owns bookkeeping; execution stays in the provider."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        provider: ModelProvider,
        router: ModelRouter,
        resources: ResourceManager | None = None,
        bus: EventBus | None = None,
        keep_warm_seconds: float = DEFAULT_KEEP_WARM_SECONDS,
        seed_mimo_edge: bool = True,
    ) -> None:
        self._registry = registry
        self._provider = provider
        self._router = router
        self._resources = resources
        self._bus = bus
        self._keep_warm_seconds = keep_warm_seconds
        self._loaded: dict[str, LoadedModel] = {}
        self.audit: list[ManagerEvent] = []
        self.seeded_ids: tuple[str, ...] = ()
        if seed_mimo_edge and len(registry) == 0:
            self.seeded_ids = seed_mimo_edge_pool(registry)
            if self.seeded_ids:
                registry.save()
                logger.info(
                    "seeded the first Model Pool (MiMo Edge, §5.6): %s",
                    ", ".join(self.seeded_ids),
                )

    # ------------------------------------------------------------ factories

    @classmethod
    def from_config(
        cls,
        models_dir: str | Path,
        *,
        provider: ModelProvider,
        resources: ResourceManager | None = None,
        bus: EventBus | None = None,
        keep_warm_seconds: int = DEFAULT_KEEP_WARM_SECONDS,
        seed_mimo_edge: bool = True,
    ) -> ModelManager:
        """Build from the §2.1 ``models`` config surface (used by the
        runtime boot)."""
        directory = Path(models_dir)
        registry = ModelRegistry(directory / REGISTRY_FILE)
        router = ModelRouter()
        return cls(
            registry=registry,
            provider=provider,
            router=router,
            resources=resources,
            bus=bus,
            keep_warm_seconds=float(keep_warm_seconds),
            seed_mimo_edge=seed_mimo_edge,
        )

    # ------------------------------------------------------------- §5.4 API

    def select(self, request: RoutingRequest) -> RoutingDecision:
        """§5.4 «select» — the §5.7 router with live resource context."""
        decision = self._router.route(self._registry.list_models(), request)
        self.audit.append(
            ManagerEvent(
                verb="select",
                model_id=decision.selected_model_id or "-",
                detail=decision.reason,
            )
        )
        return decision

    def load(self, model_id: str, *, reason: str = "explicit") -> LoadedModel:
        """§5.4 «load» — budget-check → evict idlers → provider load →
        allocation → event.

        Phase 3 semantics: ``ResourceManager.load_model`` never denies
        (over-allocation surfaces as pressure, Spec §92). The §5.4 gate
        is therefore *predictive*: check the RAM/VRAM budgets first,
        evict keep-warm idlers (LRU first) to make room, and refuse the
        load only when the model still cannot be hosted — one task
        must never crash the machine (Spec §91).
        """
        model = self._registry.get(model_id)
        if model_id in self._loaded:
            return self._loaded[model_id]
        self._publish(EventName.MODEL_LOADING, {"model_id": model_id, "backend": model.backend})
        ram_mb, vram_mb = model.ram, model.vram
        if not self._fits_budgets(ram_mb, vram_mb):
            evicted = self._evict_lru_until_fits(ram_mb, vram_mb)
            if evicted:
                logger.info("pressure: evicted keep-warm idlers %s", evicted)
        if not self._fits_budgets(ram_mb, vram_mb):
            self._mark(model_id, ModelStatus.ERROR)
            self._publish(
                EventName.MODEL_ERROR,
                {
                    "model_id": model_id,
                    "error": "resource budget refused the load",
                    "phase": "load",
                },
            )
            raise LoadRefusedError(
                f"resource budgets refuse loading {model_id!r} "
                f"(ram={ram_mb}MB, vram={vram_mb}MB) — §91/§92"
            )
        if self._resources is not None:
            self._resources.load_model(model_id, memory_mb=ram_mb, vram_mb=vram_mb)
        try:
            info = self._provider.load(model)
        except ProviderError as exc:
            if self._resources is not None:
                self._resources.unload_model(model_id)
            self._mark(model_id, ModelStatus.ERROR)
            self._publish(
                EventName.MODEL_ERROR,
                {"model_id": model_id, "error": str(exc), "phase": "load"},
            )
            raise ModelManagerError(f"provider failed to load {model_id!r}: {exc}") from exc
        # Real-footprint correction (Spec §135 «نتائج الجهاز الحقيقي بدل
        # التخمين»): swap the predictive registry estimate for the observed
        # RSS when the provider can see its runtime process (optional psutil,
        # MODE A). The budget gate above still ran on the estimate — §91/§92.
        try:
            resident = self._provider.resident_memory_mb(model_id)
        except Exception:  # noqa: BLE001 — observation must never fail a load
            resident = None
        if resident is not None and resident > 0:
            ram_mb = resident
            if self._resources is not None:
                self._resources.set_model_memory(
                    model_id, memory_mb=ram_mb, vram_mb=vram_mb
                )
        record = LoadedModel(
            model_id=model_id,
            backend=info.backend,
            loaded_at=datetime.now(UTC).isoformat(),
            ram_mb=ram_mb,
            vram_mb=vram_mb,
            last_used_monotonic=time.monotonic(),
            keep_warm_seconds=self._keep_warm_seconds,
            endpoint=info.detail,
        )
        self._loaded[model_id] = record
        self._mark(model_id, ModelStatus.LOADED)
        self._sync_warm_ids()
        self.audit.append(ManagerEvent(verb="load", model_id=model_id, detail=reason))
        self._publish(
            EventName.MODEL_LOADED,
            {
                "model_id": model_id,
                "backend": info.backend,
                "ram_mb": ram_mb,
                "vram_mb": vram_mb,
                "reason": reason,
            },
        )
        return record

    def generate(self, request: GenerateRequest) -> GenerateResult:
        """§5.4 «run» (blocking). Auto-loads when the request allows."""
        model_id = self._prepare_run(request)
        try:
            result = self._provider.generate(request)
        except ProviderError as exc:
            self._publish(
                EventName.MODEL_ERROR,
                {"model_id": model_id, "error": str(exc), "phase": "generate"},
            )
            raise
        self._touch(model_id)
        return result

    def stream(self, request: GenerateRequest) -> Iterator[StreamChunk]:
        """§5.4 «run» (streaming). Auto-loads when the request allows."""
        model_id = self._prepare_run(request)
        try:
            yield from self._provider.stream(request)
        except ProviderError as exc:
            self._publish(
                EventName.MODEL_ERROR,
                {"model_id": model_id, "error": str(exc), "phase": "stream"},
            )
            raise
        self._touch(model_id)

    def keep_warm(self, model_id: str, seconds: float | None = None) -> None:
        """§5.4 «keep warm» — extend (or query-reset) one TTL."""
        record = self._loaded_record(model_id)
        ttl = self._keep_warm_seconds if seconds is None else float(seconds)
        self._loaded[model_id] = replace(record, keep_warm_seconds=ttl)
        self.audit.append(
            ManagerEvent(verb="keep_warm", model_id=model_id, detail=f"ttl={ttl}s")
        )

    def unload(self, model_id: str, *, reason: str = "explicit") -> None:
        """§5.4 «unload» — provider release + budget release + event."""
        record = self._loaded.pop(model_id, None)
        if record is None:
            raise ModelManagerError(f"model {model_id!r} is not loaded")
        try:
            self._provider.unload(model_id)
        finally:
            if self._resources is not None:
                self._resources.unload_model(model_id)
        self._mark(model_id, ModelStatus.UNLOADED)
        self._sync_warm_ids()
        self.audit.append(ManagerEvent(verb="unload", model_id=model_id, detail=reason))
        self._publish(
            EventName.MODEL_UNLOADED,
            {"model_id": model_id, "reason": reason, "ram_mb": record.ram_mb},
        )

    def unload_idle(
        self, *, ignore_ttl: bool = False, reason: str = "idle"
    ) -> list[str]:
        """Expire keep-warm idlers; ``ignore_ttl`` drops them all (the
        Spec §92 pressure path)."""
        now = time.monotonic()
        evicted: list[str] = []
        for model_id, record in list(self._loaded.items()):
            expired = (now - record.last_used_monotonic) >= record.keep_warm_seconds
            if ignore_ttl or expired:
                self.unload(model_id, reason=reason)
                evicted.append(model_id)
        return evicted

    def _fits_budgets(self, ram_mb: int, vram_mb: int) -> bool:
        """Predictive §5.4 gate: would this load fit the RAM/VRAM model
        budgets on top of the current allocations?"""
        if self._resources is None:
            return True
        budgets = self._resources.budgets
        ram_budget = budgets.model_memory_mb or budgets.ram_mb
        vram_budget = budgets.vram_mb
        if ram_budget is not None and self._resources.model_memory_mb + ram_mb > ram_budget:
            return False
        if vram_budget is not None and self._resources.model_vram_mb + vram_mb > vram_budget:
            return False
        return True

    def _evict_lru_until_fits(self, ram_mb: int, vram_mb: int) -> list[str]:
        """Spec §92 step 2 — unload keep-warm idlers, LRU first, until
        the new model fits (or nothing is left to evict)."""
        evicted: list[str] = []
        while self._loaded and not self._fits_budgets(ram_mb, vram_mb):
            lru_id = min(
                self._loaded.items(),
                key=lambda pair: pair[1].last_used_monotonic,
            )[0]
            self.unload(lru_id, reason="pressure")
            evicted.append(lru_id)
        return evicted

    def apply_pressure(self, decision: ResourcePolicyDecision) -> list[str]:
        """React to the §4.5/§92 ladder — no «abort» exists anywhere.

        ``unload_model``  → drop the idlest resident model;
        ``switch_model``  → drop the LRU resident model so the next
        select/load picks a smaller one (the actual re-selection
        belongs to the Agent Runtime — Phase 5);
        ``reduce_*``     → no model action (concurrency/background are
        resource-side).
        """
        acted: list[str] = []
        for recommended in decision.actions:
            action = recommended.action
            if action not in ("unload_model", "switch_model"):
                continue
            if not self._loaded:
                continue
            if action == "unload_model":
                idlest = min(
                    self._loaded.items(),
                    key=lambda pair: pair[1].last_used_monotonic,
                )
            else:  # switch_model — free the LRU model to make room
                idlest = min(
                    self._loaded.items(),
                    key=lambda pair: pair[1].last_used_monotonic,
                )
            model_id = idlest[0]
            self.unload(model_id, reason=f"pressure:{action}")
            acted.append(f"{action}:{model_id}")
        return acted

    def shutdown(self) -> None:
        """Release every resident model (runtime ``shutdown`` path)."""
        for model_id in list(self._loaded):
            try:
                self.unload(model_id, reason="shutdown")
            except ModelManagerError:  # pragma: no cover - defensive
                logger.warning("shutdown: model %s already gone", model_id)
        self._provider.close()
        self._registry.save()

    # ---------------------------------------------------- §5.5 on registration

    def benchmark(
        self,
        model_id: str,
        spec: BenchmarkSpec | None = None,
        *,
        device: str | None = None,
        keep_loaded: bool = False,
    ) -> ModelBenchmark:
        """Run the §5.5 protocol for one model and persist it (Spec
        §135 step 8: «Register profile»).

        The load honors the §5.4 discipline: budget reservation first
        (via :meth:`load`, including §92 idle eviction), then the
        Spec §135 ordered protocol, then release — unless the model
        was already resident or ``keep_loaded`` is set.
        """
        model = self._registry.get(model_id)
        spec = spec or BenchmarkSpec()
        was_loaded = model_id in self._loaded
        if not was_loaded:
            self.load(model_id, reason="benchmark")
        try:
            mark = run_benchmark(
                self._provider,
                model,
                spec,
                device=device,
                memory_sampler=self._memory_sampler(),
            )
        finally:
            if not was_loaded and not keep_loaded:
                self.unload(model_id, reason="benchmark_done")
        self._registry.attach_benchmark(model_id, mark)
        self._registry.save()
        self.audit.append(
            ManagerEvent(
                verb="benchmark",
                model_id=model_id,
                detail=f"gen={mark.generation_speed} tps",
            )
        )
        return mark

    def register(self, model: Model, *, benchmark: bool = False) -> Model:
        """Register one model; §5.5 benchmark-on-registration when
        ``benchmark`` is set (requires a loadable model)."""
        record = self._registry.register(model)
        self._registry.save()
        if benchmark:
            self.benchmark(model.id)
            record = self._registry.get(model.id)
        return record

    def unregister(self, model_id: str) -> Model:
        """Drop one model — the pool is never fixed (§5.6). Loaded
        models are unloaded first."""
        if model_id in self._loaded:
            self.unload(model_id, reason="unregister")
        model = self._registry.unregister(model_id)
        self._registry.save()
        return model

    # ---------------------------------------------------------------- queries

    def registry(self) -> ModelRegistry:
        return self._registry

    def provider(self) -> ModelProvider:
        return self._provider

    def router(self) -> ModelRouter:
        return self._router

    def loaded_models(self) -> tuple[LoadedModel, ...]:
        return tuple(self._loaded.values())

    def is_loaded(self, model_id: str) -> bool:
        return model_id in self._loaded

    def health(self, model_id: str) -> ProviderHealth:
        """Delegate one health probe to the provider."""
        return self._provider.health(model_id)

    def models_by_capability(self, capability: str) -> tuple[Model, ...]:
        return self._registry.find_by_capability(capability)

    # --------------------------------------------------------------- private

    def _prepare_run(self, request: GenerateRequest) -> str:
        model_id = request.model_id
        if model_id not in self._loaded:
            if not request.auto_load:
                raise ModelManagerError(
                    f"model {model_id!r} is not loaded — load() first or set "
                    "auto_load on the request (§5.4)"
                )
            self.load(model_id, reason="auto_load")
        return model_id

    def _touch(self, model_id: str) -> None:
        record = self._loaded.get(model_id)
        if record is not None:
            self._loaded[model_id] = replace(
                record,
                last_used_monotonic=time.monotonic(),
                generations=record.generations + 1,
            )
            self.audit.append(
                ManagerEvent(verb="run", model_id=model_id, detail="generate")
            )

    def _loaded_record(self, model_id: str) -> LoadedModel:
        record = self._loaded.get(model_id)
        if record is None:
            raise ModelManagerError(f"model {model_id!r} is not loaded")
        return record

    def _mark(self, model_id: str, status: str) -> None:
        try:
            self._registry.mark_status(model_id, status)
            self._registry.save()
        except Exception:  # noqa: BLE001 — status marking must never kill a load
            logger.debug("status marking skipped for %s", model_id)

    def _sync_warm_ids(self) -> None:
        self._router.set_warm_ids(frozenset(self._loaded))

    def _publish(self, name: EventName, payload: dict[str, object]) -> None:
        if self._bus is not None:
            self._bus.publish(name, payload=payload, source="nexus.models")

    def _memory_sampler(self):
        """RAM/VRAM sampler for §5.5 — reads the ResourceManager's
        model allocations (resident totals, MB)."""

        def sample() -> tuple[int, int]:
            if self._resources is None:
                return (0, 0)
            return (
                self._resources.model_memory_mb,
                self._resources.model_vram_mb,
            )

        return sample

    # ------------------------------------------------------ resource context

    def available_ram_mb(self) -> int | None:
        """RAM still available for models: the §2.1/§4.4 budget minus
        the current model allocations (the router's §5.7 input)."""
        if self._resources is None:
            return None
        budgets = self._resources.budgets
        budget = budgets.model_memory_mb or budgets.ram_mb
        if budget is None:
            return None
        return max(0, budget - self._resources.model_memory_mb)

    def available_vram_mb(self) -> int | None:
        if self._resources is None:
            return None
        budget = self._resources.budgets.vram_mb
        if budget is None:
            return None
        return max(0, budget - self._resources.model_vram_mb)

    def workload(self) -> float:
        """0..1 saturation: resident models ÷ concurrency budget.
        Without a hardware profile the budget may be unknown (None) —
        then the count itself is the capacity (any loaded model reads
        as fully saturated, which is honest for a tiny host)."""
        loaded = len(self._loaded)
        if self._resources is None:
            return 0.0
        capacity = self._resources.budgets.max_concurrency
        if capacity is None:
            capacity = self._resources.budgets.max_agents
        if capacity is None:
            capacity = max(1, loaded)
        return min(1.0, loaded / float(max(1, capacity)))

    def route(
        self,
        request: RoutingRequest | None = None,
        **overrides: object,
    ) -> RoutingDecision:
        """Convenience ``select`` — live RAM/VRAM budgets and workload
        prefilled from the ResourceManager (§5.7 inputs)."""
        base = request or RoutingRequest()
        kwargs: dict[str, object] = dict(overrides)
        if base.ram_mb is None and "ram_mb" not in kwargs:
            kwargs["ram_mb"] = self.available_ram_mb()
        if base.vram_mb is None and "vram_mb" not in kwargs:
            kwargs["vram_mb"] = self.available_vram_mb()
        if "current_workload" not in kwargs:
            kwargs["current_workload"] = self.workload()
        merged = replace(base, **kwargs)  # type: ignore[arg-type]
        return self.select(merged)


__all__ = [
    "DEFAULT_KEEP_WARM_SECONDS",
    "LoadRefusedError",
    "LoadedModel",
    "ManagerEvent",
    "ModelManager",
    "ModelManagerError",
]
