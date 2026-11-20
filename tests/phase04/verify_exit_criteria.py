#!/usr/bin/env python3
"""Phase 4 verification harness — Final Build Plan §5 Exit Criteria.

Proves the Local Model Runtime section by section:

* A — Model Abstraction (§5.1): the ModelProvider interface — the
       seven members verbatim — plus the request/result/stream/health
       contracts and the error hierarchy.
* B — Model Registry (§5.2): the Model record with the thirteen
       verbatim fields, atomic persistence, status lifecycle,
       benchmark attachment with bounded history.
* C — llama.cpp Integration (§5.3): the adapter chain literal
       (NEXUS Model API → llama.cpp Adapter → llama-server → Model),
       argv construction, completion request encoding, response/SSE
       parsing, a full fake-server round trip, and the missing-binary
       failure mode — plus proof the manager stays backend-independent.
* D — Dynamic Loading (§5.4): select · load · run · keep warm ·
       unload per resources — budget gate, LRU idle eviction, refusal
       (Spec §91/§92), TTL expiry, pressure ladder, auto-load,
       shutdown release, and only the four §2.2 model events.
* E — Model Benchmarking (§5.5): the seven verbatim benchmark fields,
       the Spec §135 ordered protocol, persistence, and the
       measured-vs-seeded source distinction.
* F — MiMo Edge Profile (§5.6) + Model Router (§5.7) + integration:
       the five-model first pool with the Spec §88 measured baselines
       (not a fixed list), the §136 routing examples, the §178 score
       components, the runtime wiring across reboots, the event-name
       guard, and Phases 1–3 harnesses still green (98/98 · 143/143 ·
       104/104).

Run:  python tests/phase04/verify_exit_criteria.py [--root DIR]
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.core.config import NexusRuntime  # noqa: E402
from nexus.events import CANONICAL_EVENTS, EventBus  # noqa: E402
from nexus.models import (  # noqa: E402
    BACKEND_LLAMA_CPP,
    BENCHMARK_SOURCE_MEASURED,
    BENCHMARK_SOURCE_MIMO_EDGE,
    FORMAT_GGUF,
    MIMO_EDGE_DEVICE,
    MODEL_FIELDS,
    BenchmarkSpec,
    GenerateRequest,
    GenerateResult,
    LlamaCppProvider,
    LoadRefusedError,
    Model,
    ModelBenchmark,
    ModelCapability,
    ModelManager,
    ModelNotLoadedError,
    ModelProvider,
    ModelRegistry,
    ModelRouter,
    ModelScore,
    ModelStatus,
    ProviderError,
    RegistryError,
    RoutingRequest,
    SimulatedProvider,
    build_server_args,
    encode_completion_request,
    mimo_edge_pool,
    parse_completion_response,
    parse_sse_event,
    resolve_binary,
    run_benchmark,
    seed_mimo_edge_pool,
)
from nexus.models.llamacpp import LlamaServerLike  # noqa: E402
from nexus.resources import (  # noqa: E402
    PressureLevel,
    RecommendedAction,
    ResourceAction,
    ResourceBudgets,
    ResourceManager,
    ResourcePolicyDecision,
)

# --- verbatim expectations from the Final Build Plan -----------------------

#: Plan §5.1 interface members, verbatim.
PLAN_PROVIDER_MEMBERS = [
    "load", "unload", "generate", "stream", "health", "capabilities",
    "benchmark",
]

#: Plan §5.2 model fields, verbatim order.
PLAN_MODEL_FIELDS = [
    "id", "name", "format", "backend", "size", "context", "capabilities",
    "ram", "vram", "language", "benchmark", "status",
]

#: Plan §5.5 benchmark fields, verbatim.
PLAN_BENCHMARK_FIELDS = [
    "warmup", "prompt_speed", "generation_speed", "context", "ram", "vram",
    "stability",
]

#: Plan §5.4 dynamic-loading verbs, verbatim.
PLAN_DYNAMIC_VERBS = ["select", "load", "run", "keep_warm", "unload"]

#: Plan §5.6 first Model Pool, verbatim names.
PLAN_MIMO_POOL_NAMES = [
    "Qwen2.5-Coder-1.5B", "LFM2.5-1.2B", "Qwen3-0.6B", "DS-Coder-1.3B",
    "Yi-Coder-1.5B",
]

#: Spec §88 measured baselines (the user's device — not general specs).
SPEC88_TPS = {
    "qwen2.5-coder-1.5b": 9.57,
    "lfm2.5-1.2b": 7.54,
    "qwen3-0.6b": 11.66,
    "ds-coder-1.3b": 29.14,
}

#: The four §2.2 model events — the only names this module may publish.
MODEL_EVENT_NAMES = {"model.loading", "model.loaded", "model.unloaded",
                     "model.error"}


class Runner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.section = "?"

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        status = "PASS" if condition else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{status}] ({self.section}) {label}{suffix}")
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def summary(self) -> int:
        total = self.passed + self.failed
        print()
        print("=" * 72)
        print(f"PHASE 4 EXIT CRITERIA — {self.passed}/{total} checks passed"
              f" ({self.failed} failed)")
        print("=" * 72)
        return 0 if self.failed == 0 else 1


# ---------------------------------------------------------------- test doubles

class FakeLlamaServer:
    """In-process llama-server double: records argv + requests, serves
    canned completion/SSE/health responses."""

    def __init__(self, argv: Sequence[str]) -> None:
        self.argv = list(argv)
        self.endpoint = "http://127.0.0.1:65530"
        self.requests: list[tuple[str, str]] = []
        self.stopped = False

    def get_json(self, path: str) -> Any:
        self.requests.append(("GET", path))
        if path == "/health":
            return {"status": "ok"}
        return {}

    def post_json(self, path: str, payload: Mapping[str, Any]) -> Any:
        self.requests.append(("POST", path))
        n_predict = int(payload.get("n_predict", 16))
        return {
            "content": " ".join(f"w{i}" for i in range(max(1, n_predict))),
            "timings": {
                "prompt_n": 12,
                "prompt_ms": 240.0,
                "predicted_n": n_predict,
                "predicted_ms": n_predict * 100.0,
            },
        }

    def stream_sse(
        self, path: str, payload: Mapping[str, Any]
    ) -> Iterator[Mapping[str, Any]]:
        self.requests.append(("POST", path))
        n_predict = int(payload.get("n_predict", 4))
        for i in range(n_predict):
            yield {"content": f" {i}"}
        yield {
            "content": "",
            "stop": True,
            "timings": {
                "prompt_n": 6,
                "prompt_ms": 120.0,
                "predicted_n": n_predict,
                "predicted_ms": n_predict * 50.0,
            },
        }

    def alive(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True


class RecordingFactory:
    """server_factory double — records every argv the adapter built."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []
        self.servers: list[FakeLlamaServer] = []

    def __call__(self, argv: Sequence[str]) -> LlamaServerLike:
        self.argvs.append(list(argv))
        server = FakeLlamaServer(argv)
        self.servers.append(server)
        return server


def make_model(**overrides: Any) -> Model:
    """A generic test model (1 GB, 1536 MB RAM, coding+chat, 8192 ctx)."""
    base: dict[str, Any] = dict(
        id="test-model-a",
        name="Test Model A",
        format=FORMAT_GGUF,
        backend=BACKEND_LLAMA_CPP,
        size=1_000_000_000,
        context=8192,
        capabilities=(ModelCapability.CODING, ModelCapability.CHAT),
        ram=1536,
        vram=0,
        language=("en",),
    )
    base.update(overrides)
    return Model(**base)


def make_manager(
    base: str,
    *,
    ram_mb: int = 65536,
    vram_mb: int | None = 0,
    keep_warm: float = 300.0,
    bus: EventBus | None = None,
    seed: bool = True,
) -> tuple[ModelManager, ResourceManager, SimulatedProvider]:
    """A manager over the simulated provider with pinned budgets."""
    resources = ResourceManager(
        f"{base}-res",
        budgets=ResourceBudgets(
            ram_mb=ram_mb, model_memory_mb=ram_mb, vram_mb=vram_mb,
            max_concurrency=4,
        ),
    )
    provider = SimulatedProvider()
    manager = ModelManager.from_config(
        f"{base}-models",
        provider=provider,
        resources=resources,
        bus=bus,
        keep_warm_seconds=keep_warm,
        seed_mimo_edge=seed,
    )
    return manager, resources, provider


# ------------------------------------------------------------------- sections

def section_a(runner: Runner) -> None:
    """A — Model Abstraction (§5.1)."""
    runner.section = "A/§5.1"

    abstract = ModelProvider.__abstractmethods__
    runner.check(
        "ModelProvider exposes exactly the seven §5.1 members",
        set(PLAN_PROVIDER_MEMBERS) == set(abstract),
        detail=f"abstractmethods={sorted(abstract)}",
    )

    request_fields = {f.name for f in dc_fields(GenerateRequest)}
    # Phase 11 (Plan §12.2) added the optional `images` field — the
    # §5.1 text contract stays byte for byte, so the assertion is
    # now forward-tolerant (contract present), the Phase-10 lesson.
    runner.check(
        "GenerateRequest carries the NEXUS Model API contract",
        {"model_id", "prompt", "system", "max_tokens", "temperature",
         "top_p", "stop", "seed", "auto_load"} <= request_fields,
        detail=f"fields={sorted(request_fields)}",
    )
    result_fields = {f.name for f in dc_fields(GenerateResult)}
    runner.check(
        "GenerateResult carries text + token/time accounting",
        {"model_id", "backend", "text", "prompt_tokens", "generation_tokens",
         "prompt_seconds", "generation_seconds"} == result_fields,
    )

    sim = SimulatedProvider()
    model = make_model()
    info = sim.load(model)
    runner.check("load returns LoadInfo(model_id, backend)",
                 info.model_id == model.id and info.backend == "simulated")

    result = sim.generate(GenerateRequest(model_id=model.id, prompt="one two",
                                          max_tokens=16))
    runner.check(
        "generate returns accounting (prompt + generation tokens/seconds)",
        result.prompt_tokens == 2 and result.generation_tokens == 16
        and result.prompt_seconds is not None
        and result.generation_seconds is not None,
        detail=f"pps={result.prompt_tokens_per_second}",
    )

    chunks = list(sim.stream(GenerateRequest(model_id=model.id, prompt="x",
                                             max_tokens=3)))
    runner.check(
        "stream yields deltas with a final done chunk carrying stats",
        chunks[-1].done and chunks[-1].result is not None
        and all(not c.done for c in chunks[:-1]) and chunks[0].delta != "",
        detail=f"chunks={len(chunks)}",
    )

    health = sim.health(model.id)
    runner.check("health reports ok for a resident model",
                 health.ok and health.status == "ok")
    sim.unload(model.id)
    health2 = sim.health(model.id)
    runner.check("health reports not_loaded after unload",
                 not health2.ok and health2.status == "not_loaded")
    sim.load(model)
    runner.check("capabilities mirror the model record",
                 ModelCapability.CODING in sim.capabilities(model.id))

    try:
        sim.generate(GenerateRequest(model_id="ghost", prompt="x"))
        runner.check("generate on unknown/unloaded model raises", False)
    except ProviderError:
        runner.check("generate on unknown/unloaded model raises", True)

    runner.check(
        "error hierarchy: ModelNotLoadedError is a ProviderError",
        issubclass(ModelNotLoadedError, ProviderError),
    )


def section_b(runner: Runner, base: Path) -> None:
    """B — Model Registry (§5.2)."""
    runner.section = "B/§5.2"

    field_names = [f.name for f in dc_fields(Model)]
    runner.check(
        "Model carries the twelve §5.2 fields (+2 documented auxiliary)",
        PLAN_MODEL_FIELDS == field_names[:12],
        detail=f"fields={field_names}",
    )
    runner.check("MODEL_FIELDS constant matches the plan verbatim",
                 list(MODEL_FIELDS) == PLAN_MODEL_FIELDS)

    registry_path = base / "models" / "models.registry.json"
    registry = ModelRegistry(registry_path)
    model = make_model()
    registry.register(model)
    runner.check("register + get round trip",
                 registry.get(model.id).name == "Test Model A")
    runner.check("find returns None for unknown ids",
                 registry.find("nope") is None)
    try:
        registry.register(make_model())
        runner.check("duplicate registration rejected", False)
    except RegistryError:
        runner.check("duplicate registration rejected", True)

    registry.attach_benchmark(
        model.id, ModelBenchmark(generation_speed=12.5, source="measured")
    )
    runner.check("benchmark attaches + status → benchmarked",
                 registry.get(model.id).benchmark is not None
                 and registry.get(model.id).status == ModelStatus.BENCHMARKED)
    registry.mark_status(model.id, ModelStatus.LOADED)
    runner.check("status lifecycle mutable via mark_status",
                 registry.get(model.id).status == ModelStatus.LOADED)

    registry.unregister(model.id)
    runner.check("unregister drops the record (pool not fixed)",
                 registry.find(model.id) is None)
    try:
        registry.get(model.id)
        runner.check("get on unknown id raises RegistryError", False)
    except RegistryError:
        runner.check("get on unknown id raises RegistryError", True)

    # persistence round-trip (atomic)
    r2 = ModelRegistry(registry_path)
    r2.register(make_model(benchmark=ModelBenchmark(generation_speed=9.9)))
    r2.register(make_model(id="test-model-b", name="B", ram=512))
    path = r2.save()
    runner.check("save is atomic (no .tmp residue)",
                 not Path(str(path) + ".tmp").exists())
    r3 = ModelRegistry(registry_path)
    runner.check(
        "persistence round trip — record + benchmark survive reload",
        len(r3) == 2
        and r3.get("test-model-a").benchmark is not None
        and r3.get("test-model-a").benchmark.generation_speed == 9.9
        and r3.get("test-model-b").ram == 512,
    )
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    runner.check(
        "registry file carries schema/version markers",
        raw.get("schema") == "nexus.models.registry"
        and raw.get("version") == 1,
    )

    # bounded benchmark history (fresh file)
    r4 = ModelRegistry(base / "models" / "history.registry.json")
    r4.register(make_model())
    for i in range(12):
        r4.attach_benchmark("test-model-a",
                            ModelBenchmark(generation_speed=float(i)))
    history = r4.get("test-model-a").benchmark_history
    runner.check("benchmark history bounded at 8 runs",
                 len(history) == 8 and history[-1].generation_speed == 11.0)

    runner.check("find_by_capability filters",
                 {m.id for m in r4.find_by_capability("coding")}
                 == {"test-model-a"})
    runner.check("summaries expose id/name/backend/status",
                 r4.summaries()[0].id == "test-model-a")


def section_c(runner: Runner) -> None:
    """C — llama.cpp Integration (§5.3)."""
    runner.section = "C/§5.3"

    argv = build_server_args(
        model_path="M:/NEXUS/models/test.gguf", context=8192,
        host="127.0.0.1", port=8081, gpu_layers=99, threads=8,
        kv_quant="q4_0", extra_args=["--verbose"], binary="llama-server",
    )
    expected = [
        "llama-server", "-m", "M:/NEXUS/models/test.gguf", "-c", "8192",
        "--host", "127.0.0.1", "--port", "8081", "-ngl", "99", "-t", "8",
        "-ctk", "q4_0", "-ctv", "q4_0", "--verbose",
    ]
    runner.check("server argv: -m/-c/--host/--port/-ngl/-t + KV-Q4 flags",
                 argv == expected, detail=str(argv))

    argv_cpu = build_server_args(model_path="x.gguf", context=2048,
                                 host="127.0.0.1", port=0)
    runner.check(
        "CPU defaults: -ngl 0, no threads flag, no KV quant",
        argv_cpu[argv_cpu.index("-ngl") + 1] == "0"
        and "-t" not in argv_cpu and "-ctk" not in argv_cpu,
    )

    body = json.loads(encode_completion_request(
        GenerateRequest(model_id="m", prompt="USER TEXT", system="SYS",
                        max_tokens=64, temperature=0.4, top_p=0.9,
                        stop=("STOP", "END"), seed=7),
        stream=False,
    ))
    runner.check(
        "completion body: system+prompt, n_predict, sampling, stop, seed",
        body["prompt"] == "SYS\n\nUSER TEXT" and body["n_predict"] == 64
        and body["temperature"] == 0.4 and body["top_p"] == 0.9
        and body["stop"] == ["STOP", "END"] and body["seed"] == 7
        and body["stream"] is False,
    )
    body_stream = json.loads(encode_completion_request(
        GenerateRequest(model_id="m", prompt="p"), stream=True))
    runner.check("stream flag switches in the same encoder",
                 body_stream["stream"] is True)

    payload = {
        "content": "hello world",
        "timings": {"prompt_n": 10, "prompt_ms": 100.0,
                    "predicted_n": 20, "predicted_ms": 2000.0},
    }
    result = parse_completion_response(payload, "m")
    runner.check(
        "response parsing: text + prompt/gen tokens + seconds",
        result.text == "hello world" and result.prompt_tokens == 10
        and result.generation_tokens == 20
        and result.generation_tokens_per_second == 10.0
        and result.prompt_tokens_per_second == 100.0,
    )
    mid = parse_sse_event({"content": " par"}, "m")
    runner.check("SSE delta parsing (not done)",
                 mid.delta == " par" and not mid.done and mid.result is None)
    last = parse_sse_event({"content": "", "stop": True,
                            "timings": payload["timings"]}, "m")
    runner.check("SSE final event carries the full stats",
                 last.done and last.result is not None
                 and last.result.generation_tokens == 20)

    try:
        resolve_binary("nexus-no-such-llama-server-xyz")
        runner.check("missing binary raises a clear ProviderError", False)
    except ProviderError as exc:
        runner.check("missing binary raises a clear ProviderError",
                     "llama-server" in str(exc))

    # Full fake-server chain: Model API → Adapter → llama-server → Model
    factory = RecordingFactory()
    provider = LlamaCppProvider(models_dir="M:/NEXUS/models",
                                server_factory=factory)
    runner.check("adapter identifies as the llama.cpp backend",
                 provider.backend == BACKEND_LLAMA_CPP)
    model = make_model()
    info = provider.load(model)
    runner.check(
        "chain: adapter spawned llama-server with -m <model path>",
        len(factory.argvs) == 1
        and factory.argvs[0][factory.argvs[0].index("-m") + 1]
        == "M:/NEXUS/models/test-model-a.gguf",
        detail=str(factory.argvs[0][:4]),
    )
    runner.check("LoadInfo exposes the backend + endpoint",
                 info.backend == "llama.cpp" and info.handle is not None)

    result = provider.generate(
        GenerateRequest(model_id=model.id, prompt="bench", max_tokens=5)
    )
    server = factory.servers[0]
    runner.check(
        "generate POSTed /completion on the spawned server",
        ("POST", "/completion") in server.requests
        and result.generation_tokens == 5 and result.text.startswith("w0"),
    )
    chunks = list(provider.stream(
        GenerateRequest(model_id=model.id, prompt="s", max_tokens=4)))
    runner.check("stream consumed the SSE endpoint and ended done",
                 chunks[-1].done and chunks[-1].result is not None
                 and len(chunks) == 5)
    health = provider.health(model.id)
    runner.check("health GET /health → ok while the server lives",
                 health.ok and health.status == "ok")
    provider.unload(model.id)
    runner.check("unload stopped the llama-server process",
                 server.stopped and not provider.loaded_ids())

    # Backend independence (Spec §93/§137): the manager knows providers
    # only through the abstraction.
    import nexus.models.manager as manager_module

    source = Path(manager_module.__file__).read_text(encoding="utf-8")
    runner.check(
        "ModelManager never imports the llama.cpp adapter directly",
        "llamacpp" not in source and "LlamaCpp" not in source,
    )
    runner.check(
        "runtime swap: the same §5.1 interface drives the simulated backend",
        isinstance(SimulatedProvider(), ModelProvider)
        and isinstance(LlamaCppProvider(server_factory=RecordingFactory()),
                       ModelProvider),
    )


def section_d(runner: Runner, base: Path) -> None:
    """D — Dynamic Loading (§5.4)."""
    runner.section = "D/§5.4"

    bus = EventBus()
    events: list[tuple[str, dict[str, Any]]] = []
    bus.subscribe("model.*", lambda e: events.append((e.name, dict(e.payload))))

    manager, resources, _ = make_manager(
        str(base), ram_mb=4096, vram_mb=0, keep_warm=300.0, bus=bus, seed=True
    )
    for verb in PLAN_DYNAMIC_VERBS:
        if verb == "run":  # §5.4 «run» is served by generate + stream
            present = callable(getattr(manager, "generate", None)) and callable(
                getattr(manager, "stream", None)
            )
        else:
            present = callable(getattr(manager, verb, None))
        runner.check(f"§5.4 verb «{verb}» present on the ModelManager", present)

    # select → load → run → stream → keep warm → unload (the §5.4 cycle)
    decision = manager.route(RoutingRequest(task_type="coding", ram_mb=4096,
                                            vram_mb=0))
    runner.check("select returns a model id from the §5.7 router",
                 decision.selected_model_id is not None)
    target = decision.selected_model_id or ""
    record = manager.load(target)
    runner.check(
        "load reserves RAM in the ResourceManager",
        resources.model_memory_mb == manager.registry().get(target).ram
        and record.model_id == target,
        detail=f"allocated={resources.model_memory_mb}MB",
    )
    runner.check(
        "events fire in order: model.loading → model.loaded",
        [n for n, _ in events] == ["model.loading", "model.loaded"],
    )

    result = manager.generate(GenerateRequest(model_id=target, prompt="go",
                                              max_tokens=8))
    runner.check("run (generate) goes through the provider",
                 result.model_id == target and result.generation_tokens == 8)
    chunks = list(manager.stream(GenerateRequest(model_id=target, prompt="s",
                                                 max_tokens=3)))
    runner.check("run (stream) yields chunks and updates liveness",
                 chunks[-1].done
                 and manager.loaded_models()[0].generations == 2)

    manager.keep_warm(target, seconds=3600.0)
    runner.check("keep warm extends the TTL",
                 manager.loaded_models()[0].keep_warm_seconds == 3600.0)
    evicted = manager.unload_idle()
    runner.check("extended TTL survives an idle sweep",
                 evicted == [] and manager.is_loaded(target))

    manager.unload(target, reason="explicit")
    runner.check(
        "unload releases the provider AND the ResourceManager allocation",
        not manager.is_loaded(target)
        and resources.model_memory_mb == 0
        and target not in resources.models,
    )
    runner.check(
        "model.unloaded fired with the reason payload",
        events[-1][0] == "model.unloaded"
        and events[-1][1].get("reason") == "explicit",
    )

    # §5.4 auto-load path
    auto = manager.generate(GenerateRequest(model_id="qwen3-0.6b",
                                            prompt="auto", max_tokens=4,
                                            auto_load=True))
    runner.check("auto_load request loads on demand",
                 auto.model_id == "qwen3-0.6b"
                 and manager.is_loaded("qwen3-0.6b"))
    manager.unload("qwen3-0.6b", reason="cleanup")

    # Budget refusal (Spec §91/§92) — never crash the machine
    manager2, resources2, _ = make_manager(
        str(base) + "2", ram_mb=1024, vram_mb=0, seed=True
    )
    try:
        manager2.load("qwen2.5-coder-1.5b")  # needs 2048 MB > 1024 budget
        runner.check("over-budget load refuses (LoadRefusedError)", False)
    except LoadRefusedError:
        runner.check("over-budget load refuses (LoadRefusedError)", True)
    runner.check(
        "refusal leaves the registry marked error and nothing resident",
        manager2.registry().get("qwen2.5-coder-1.5b").status
        == ModelStatus.ERROR
        and resources2.model_memory_mb == 0
        and not manager2.is_loaded("qwen2.5-coder-1.5b"),
    )

    # LRU idle eviction to make room (Spec §92 «unload idle model»)
    manager3, resources3, _ = make_manager(
        str(base) + "3", ram_mb=4096, vram_mb=0, seed=True
    )
    manager3.load("qwen3-0.6b")      # 1024
    manager3.load("lfm2.5-1.2b")     # +1792 = 2816
    manager3.load("qwen2.5-coder-1.5b")  # +2048 = 4864 > 4096 → evict qwen3
    runner.check(
        "pressure load evicts the LRU idler and succeeds",
        manager3.is_loaded("qwen2.5-coder-1.5b")
        and not manager3.is_loaded("qwen3-0.6b")
        and resources3.model_memory_mb == 1792 + 2048,
        detail=f"alloc={resources3.model_memory_mb}",
    )

    # keep-warm TTL expiry (seconds=0 → immediately idle)
    manager4, _, _ = make_manager(str(base) + "4", ram_mb=65536,
                                  keep_warm=0.0, seed=True)
    manager4.load("qwen3-0.6b")
    expired = manager4.unload_idle()
    runner.check("idle TTL expiry unloads the resident model",
                 expired == ["qwen3-0.6b"]
                 and not manager4.is_loaded("qwen3-0.6b"))

    # §4.5/§92 pressure ladder reaction
    manager5, _, _ = make_manager(str(base) + "5", ram_mb=65536, seed=True)
    manager5.load("qwen3-0.6b")
    manager5.load("lfm2.5-1.2b")
    decision92 = ResourcePolicyDecision(
        pressures={},
        actions=(
            RecommendedAction(action=ResourceAction.UNLOAD_MODEL,
                              reason="ram high", severity=PressureLevel.HIGH,
                              source="ram"),
        ),
        degraded=True,
        summary="ram high",
    )
    acted = manager5.apply_pressure(decision92)
    runner.check(
        "apply_pressure(unload_model) drops the idlest resident model",
        acted == ["unload_model:qwen3-0.6b"]
        and not manager5.is_loaded("qwen3-0.6b")
        and manager5.is_loaded("lfm2.5-1.2b"),
        detail=str(acted),
    )
    switch = ResourcePolicyDecision(
        pressures={},
        actions=(
            RecommendedAction(action=ResourceAction.SWITCH_MODEL,
                              reason="vram critical",
                              severity=PressureLevel.CRITICAL, source="vram"),
        ),
        degraded=True,
        summary="vram critical",
    )
    acted2 = manager5.apply_pressure(switch)
    runner.check(
        "apply_pressure(switch_model) frees the LRU model for the switch",
        acted2 == ["switch_model:lfm2.5-1.2b"]
        and not manager5.loaded_models(),
    )

    # shutdown releases everything
    manager6, resources6, _ = make_manager(str(base) + "6", ram_mb=65536,
                                           seed=True)
    manager6.load("qwen3-0.6b")
    manager6.load("lfm2.5-1.2b")
    manager6.shutdown()
    runner.check(
        "shutdown unloads every resident model + closes the provider",
        not manager6.loaded_models() and resources6.model_memory_mb == 0,
    )

    # Event-name discipline: only the four §2.2 model events, all ⊆ 28
    names = {n for n, _ in events}
    runner.check(
        "only the four §2.2 model events are published (28 registry intact)",
        names <= MODEL_EVENT_NAMES and MODEL_EVENT_NAMES <= CANONICAL_EVENTS,
        detail=str(sorted(names)),
    )


def section_e(runner: Runner, base: Path) -> None:
    """E — Model Benchmarking (§5.5)."""
    runner.section = "E/§5.5"

    bench_fields = [f.name for f in dc_fields(ModelBenchmark)]
    runner.check(
        "ModelBenchmark carries the seven §5.5 fields verbatim",
        PLAN_BENCHMARK_FIELDS == bench_fields[:7],
        detail=f"fields={bench_fields}",
    )

    # Spec §135 literal order via the simulated provider's call log
    provider = SimulatedProvider(speed_tps=25.0)
    model = make_model(id="bench-model", name="Bench")
    spec = BenchmarkSpec(warmup_runs=1, prompt_tokens=64,
                         generation_tokens=16, stability_runs=2)
    mark = run_benchmark(provider, model, spec, device="test-device",
                         memory_sampler=lambda: (1536, 0))
    log = provider.call_log
    runner.check(
        "Spec §135 order: load → warm-up → prompt bench → generation "
        "bench → memory → stability",
        log[0].startswith("load:") and log[1].startswith("generate:")
        and len([e for e in log if e.startswith("generate:")]) == 5,
        detail=str(log),
    )
    runner.check(
        "benchmark fields measured: warmup, speeds, context, RAM/VRAM, stability",
        mark.warmup is True
        and mark.prompt_speed is not None and mark.prompt_speed > 0
        and mark.generation_speed is not None
        and abs(mark.generation_speed - 25.0) < 1.0
        and mark.context == model.context
        and mark.ram == 1536 and mark.vram == 0
        and mark.stability == 1.0,
        detail=f"gen={mark.generation_speed} tps, stability={mark.stability}",
    )
    runner.check("benchmark provenance: source measured + device + timestamp",
                 mark.source == BENCHMARK_SOURCE_MEASURED
                 and mark.device == "test-device"
                 and mark.measured_at is not None)

    # persistence through the manager (§5.5 «ثم يحفظ benchmark»)
    manager, resources, _ = make_manager(str(base) + "e", ram_mb=65536,
                                         seed=False)
    manager.register(make_model())
    mark2 = manager.benchmark("test-model-a")
    runner.check(
        "manager benchmark wraps the §5.4 discipline (load → run → release)",
        not manager.is_loaded("test-model-a")
        and resources.model_memory_mb == 0
        and mark2.generation_speed is not None,
    )
    record = manager.registry().get("test-model-a")
    runner.check(
        "benchmark persisted on the registry record + status benchmarked",
        record.benchmark is not None
        and record.status in (ModelStatus.BENCHMARKED, ModelStatus.UNLOADED)
        and len(record.benchmark_history) == 1,
    )
    reloaded = ModelRegistry(Path(str(base) + "e-models") / "models.registry.json")
    runner.check(
        "benchmark survives a registry reload (real results, not guesses)",
        reloaded.get("test-model-a").benchmark is not None
        and reloaded.get("test-model-a").benchmark.stability == 1.0,
    )

    runner.check(
        "seeded vs measured sources are distinguishable",
        mimo_edge_pool()[0].benchmark.source == BENCHMARK_SOURCE_MIMO_EDGE
        and mark.source == BENCHMARK_SOURCE_MEASURED,
    )


def section_f(runner: Runner, root: Path) -> None:
    """F — MiMo Edge Profile (§5.6) + Model Router (§5.7) + integration."""
    runner.section = "F/§5.6–§5.7"

    pool = mimo_edge_pool()
    runner.check("the first Model Pool is exactly the five §5.6 models",
                 [m.name for m in pool] == PLAN_MIMO_POOL_NAMES)
    runner.check(
        "pool is llama.cpp/GGUF tiny models with capabilities + language",
        all(m.backend == BACKEND_LLAMA_CPP and m.format == FORMAT_GGUF
            and m.capabilities and m.language for m in pool),
    )
    for model_id, tps in SPEC88_TPS.items():
        seeded = next(m for m in pool if m.id == model_id)
        ok = (seeded.benchmark is not None
              and abs((seeded.benchmark.generation_speed or 0) - tps) < 0.01
              and seeded.benchmark.context == 8192)
        runner.check(f"Spec §88 baseline carried: {model_id} @ {tps} tok/s", ok)
    yi = next(m for m in pool if m.id == "yi-coder-1.5b")
    runner.check(
        "Yi-Coder-1.5B honestly awaits its on-device benchmark",
        yi.benchmark is None and yi.status == ModelStatus.REGISTERED,
    )
    qwen3 = next(m for m in pool if m.id == "qwen3-0.6b")
    runner.check(
        "§88 device learnings kept: KV-Q4 note on Qwen3-0.6B",
        qwen3.benchmark.notes.get("kv_quant") == "q4_0"
        and qwen3.benchmark.device == MIMO_EDGE_DEVICE,
    )
    ds = next(m for m in pool if m.id == "ds-coder-1.3b")
    runner.check("§88 DS-Coder measured with GPU offload",
                 bool(ds.benchmark.notes.get("gpu_offload")) and ds.vram > 0)

    # seeding is idempotent and the pool is NOT fixed (§5.6)
    with tempfile.TemporaryDirectory() as td:
        registry = ModelRegistry(Path(td) / "models.registry.json")
        seeded = seed_mimo_edge_pool(registry)
        reseeded = seed_mimo_edge_pool(registry)
        runner.check("seeding is idempotent (once, never re-forced)",
                     len(seeded) == 5 and reseeded == ())
        dropped = registry.unregister("yi-coder-1.5b")
        custom = Model(id="my-model", name="My Model", ram=512, context=4096,
                       capabilities=(ModelCapability.CODING,))
        registry.register(custom)
        runner.check(
            "the pool is open: unregister + custom registration work",
            dropped.id == "yi-coder-1.5b" and "my-model" in registry,
        )

    # §5.7 router — inputs verbatim, output = selected model id
    request_fields = {f.name for f in dc_fields(RoutingRequest)}
    runner.check(
        "RoutingRequest carries the §5.7 inputs verbatim",
        {"task_type", "complexity", "required_capability", "ram_mb",
         "vram_mb", "current_workload"} <= request_fields,
    )

    manager, _, _ = make_manager(str(root) + "-f", ram_mb=4096, vram_mb=0,
                                 seed=True)
    router = ModelRouter()
    decision = router.route(
        tuple(mimo_edge_pool()),
        RoutingRequest(task_type="coding", complexity=0.5, ram_mb=4096,
                       vram_mb=0),
    )
    runner.check(
        "router output is a selected model id (§5.7 literal)",
        isinstance(decision.selected_model_id, str)
        and decision.selected_model_id in SPEC88_TPS,
        detail=str(decision.selected_model_id),
    )
    components = {f.name for f in dc_fields(ModelScore)}
    runner.check(
        "ModelScore exposes the Spec §178 components",
        {"task_fit", "capabilities", "ram", "vram", "latency", "context",
         "reliability"} <= components,
    )

    # Spec §136 routing examples, literal
    def pick(task_type: str, **kw: Any) -> str | None:
        d = manager.route(RoutingRequest(task_type=task_type, ram_mb=4096,
                                         vram_mb=0, **kw))
        return d.selected_model_id

    runner.check("§136 «Delete file → Fast tiny»: quick_action → qwen3-0.6b",
                 pick("quick_action") == "qwen3-0.6b")
    runner.check(
        "§136 «General chat → Small general»: chat → a small chat model",
        pick("chat") in ("qwen3-0.6b", "lfm2.5-1.2b"),
    )
    runner.check(
        "§136 «Coding → Coder»: coding → a coder model",
        pick("coding") in ("qwen2.5-coder-1.5b", "ds-coder-1.3b",
                           "yi-coder-1.5b"),
    )
    runner.check(
        "§136 «Large project analysis → Long-context candidate»",
        pick("long_context") is not None
        and manager.registry().get(pick("long_context") or "").context >= 8192,
    )
    vision = manager.route(RoutingRequest(task_type="vision", ram_mb=4096))
    runner.check(
        "§136 «Image/screen → Vision»: no vision model → honest None + reason",
        vision.selected_model_id is None and "no eligible" in vision.reason,
    )
    speech = manager.route(RoutingRequest(task_type="speech", ram_mb=4096))
    runner.check("§136 «Speech → Speech model»: honest None in this pool",
                 speech.selected_model_id is None)

    # VRAM filter (§5.7 RAM/VRAM inputs)
    d_gpu = manager.route(RoutingRequest(task_type="coding", ram_mb=65536,
                                         vram_mb=0))
    runner.check(
        "VRAM budget filters DS-Coder out on a CPU-only host",
        d_gpu.selected_model_id != "ds-coder-1.3b",
    )

    # workload + warm bonus (§87 current load)
    router2 = ModelRouter(warm_ids=frozenset({"lfm2.5-1.2b"}))
    d_warm = router2.route(
        tuple(mimo_edge_pool()),
        RoutingRequest(task_type="chat", ram_mb=4096, vram_mb=0,
                       current_workload=0.8),
    )
    runner.check(
        "current workload favors the already-warm model (§87)",
        d_warm.selected_model_id == "lfm2.5-1.2b",
        detail=str(d_warm.selected_model_id),
    )

    # complexity input matters (§5.7)
    low = router.route(tuple(mimo_edge_pool()),
                       RoutingRequest(task_type="long_context",
                                      complexity=0.0, ram_mb=4096, vram_mb=0))
    high = router.route(tuple(mimo_edge_pool()),
                        RoutingRequest(task_type="long_context",
                                       complexity=1.0, ram_mb=4096, vram_mb=0))
    runner.check(
        "complexity shifts the ranking (depth over cheapness)",
        low.selected_model_id != high.selected_model_id,
        detail=f"low={low.selected_model_id} high={high.selected_model_id}",
    )

    # Integration: runtime wiring, persistence across reboots, events
    bus = EventBus()
    started_events: list[dict[str, Any]] = []
    bus.subscribe("system.started",
                  lambda e: started_events.append(dict(e.payload)))
    rt = NexusRuntime.boot(root, bus=bus, model_provider=SimulatedProvider())
    model_manager = rt.model_manager
    runner.check("runtime wires the ModelManager (§5 wiring)",
                 isinstance(model_manager, ModelManager))
    runner.check("system.started payload reports phase >= 4",
                 any((p.get("phase") or 0) >= 4 for p in started_events))
    runner.check("first boot seeds the §5.6 pool (5 models)",
                 len(model_manager.registry()) == 5
                 and len(model_manager.seeded_ids) == 5)
    custom = Model(id="persist-model", name="Persist", ram=256, context=2048,
                   capabilities=(ModelCapability.CHAT,))
    model_manager.register(custom)
    rt.shutdown()

    bus2 = EventBus()
    model_events: list[str] = []
    bus2.subscribe("model.*", lambda e: model_events.append(e.name))
    rt2 = NexusRuntime.boot(root, bus=bus2,
                            model_provider=SimulatedProvider())
    mm2 = rt2.model_manager
    runner.check(
        "reboot: registry persisted, no re-seed, custom model survives",
        len(mm2.registry()) == 6 and mm2.seeded_ids == ()
        and "persist-model" in mm2.registry(),
    )
    mm2.load("qwen3-0.6b")
    rt2.shutdown()
    runner.check(
        "runtime shutdown unloads resident models (§5.4 release)",
        not mm2.loaded_models()
        and "model.unloaded" in model_events
        and set(model_events) <= MODEL_EVENT_NAMES,
    )

    # config: the §5 additive keys parse + validate
    cfg = rt2.config.models
    runner.check(
        "models config: llama_server/host/port + keep_warm_seconds present",
        cfg.llama_server == "llama-server" and cfg.llama_host == "127.0.0.1"
        and cfg.llama_port == 0 and cfg.keep_warm_seconds == 300,
    )

    # regression: Phases 1–3 harnesses stay green
    for phase, phrase in (("phase01", "98/98"), ("phase02", "143/143"),
                          ("phase03", "104/104")):
        proc = subprocess.run(
            [sys.executable,
             str(REPO_ROOT / "tests" / phase / "verify_exit_criteria.py")],
            capture_output=True, text=True, timeout=600,
            cwd=str(REPO_ROOT),
        )
        runner.check(
            f"{phase} harness still green ({phrase})",
            proc.returncode == 0 and phrase in proc.stdout,
        )


# ---------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=str, default=None,
                        help="runtime root for the integration section")
    args = parser.parse_args()

    runner = Runner()
    print("PHASE 4 — LOCAL MODEL RUNTIME (Final Build Plan §5)")
    print()

    base = Path(tempfile.mkdtemp(prefix="nexus-phase4-"))
    root = Path(args.root) if args.root else Path(
        tempfile.mkdtemp(prefix="nexus-phase4-root-"))

    section_a(runner)
    print()
    section_b(runner, base)
    print()
    section_c(runner)
    print()
    section_d(runner, base)
    print()
    section_e(runner, base)
    print()
    section_f(runner, root)

    return runner.summary()


if __name__ == "__main__":
    raise SystemExit(main())
