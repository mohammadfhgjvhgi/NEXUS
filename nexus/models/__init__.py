"""NEXUS Model Manager (Final Build Plan §5 — Local Model Runtime).

Phase 4 module map:

* ``provider``    — the §5.1 ``ModelProvider`` interface (seven members,
                     verbatim) + the request/result/stream/health
                     contracts of the NEXUS Model API
* ``registry``    — the §5.2 ``Model`` record (thirteen fields,
                     verbatim) + the persistent Model Registry
* ``benchmark``   — the §5.5 ``ModelBenchmark`` (seven fields) + the
                     Spec §135 ordered benchmark protocol
* ``router``      — the §5.7 ``ModelRouter`` (inputs verbatim →
                     selected model id; Spec §178 score components)
* ``llamacpp``    — the §5.3 llama.cpp Adapter over ``llama-server``
                     (ggml-org/llama.cpp — the primary local inference
                     backend)
* ``manager``     — the §5.4 Model Manager: select · load · run ·
                     keep warm · unload, all per resources (Spec §91/§92)
* ``mimo``        — the §5.6 MiMo Edge first Model Pool seeded with
                     the user's measured baselines (Spec §88)
* ``simulated``   — a deterministic in-process provider (harness +
                     no-backend fallback)

Events: this module publishes only the four §2.2 model events —
``model.loading``, ``model.loaded``, ``model.unloaded``,
``model.error``. The 28-event registry stays authoritative.

مدير النماذج — المرحلة الرابعة: الواجهة والسجل والقياس والموجّه ومحوّل
llama.cpp و«الحمل الديناميكي وفق الموارد» — stdlib فقط.
"""

from .benchmark import (
    BENCHMARK_SOURCE_MEASURED,
    BENCHMARK_SOURCE_MIMO_EDGE,
    BenchmarkSpec,
    ModelBenchmark,
    run_benchmark,
)
from .llamacpp import (
    DEFAULT_BINARY,
    KV_QUANT_Q4_0,
    LlamaCppProvider,
    LlamaServerProcess,
    build_server_args,
    encode_completion_request,
    parse_completion_response,
    parse_sse_event,
    resolve_binary,
)
from .manager import (
    DEFAULT_KEEP_WARM_SECONDS,
    LoadedModel,
    LoadRefusedError,
    ManagerEvent,
    ModelManager,
    ModelManagerError,
)
from .mimo import (
    MIMO_EDGE_DEVICE,
    mimo_edge_pool,
    seed_mimo_edge_pool,
)
from .provider import (
    ALL_CAPABILITIES,
    GenerateRequest,
    GenerateResult,
    LoadInfo,
    ModelCapability,
    ModelNotLoadedError,
    ModelProvider,
    ProviderError,
    ProviderHealth,
    StreamChunk,
    UnsupportedModelError,
)
from .registry import (
    BACKEND_LLAMA_CPP,
    FORMAT_GGUF,
    MODEL_FIELDS,
    Model,
    ModelRegistry,
    ModelStatus,
    ModelSummary,
    RegistryError,
    new_model_id,
)
from .router import (
    SCORE_WEIGHTS,
    TASK_CAPABILITY_MAP,
    TASK_MIN_CONTEXT,
    ModelRouter,
    ModelScore,
    RoutingDecision,
    RoutingRequest,
)
from .simulated import SimulatedProvider

__all__ = [
    "ALL_CAPABILITIES",
    "BACKEND_LLAMA_CPP",
    "BENCHMARK_SOURCE_MEASURED",
    "BENCHMARK_SOURCE_MIMO_EDGE",
    "BenchmarkSpec",
    "DEFAULT_BINARY",
    "DEFAULT_KEEP_WARM_SECONDS",
    "FORMAT_GGUF",
    "GenerateRequest",
    "GenerateResult",
    "KV_QUANT_Q4_0",
    "LoadInfo",
    "LoadRefusedError",
    "LoadedModel",
    "LlamaCppProvider",
    "LlamaServerProcess",
    "MIMO_EDGE_DEVICE",
    "ManagerEvent",
    "MODEL_FIELDS",
    "Model",
    "ModelBenchmark",
    "ModelCapability",
    "ModelManager",
    "ModelManagerError",
    "ModelNotLoadedError",
    "ModelProvider",
    "ModelRegistry",
    "ModelRouter",
    "ModelScore",
    "ModelStatus",
    "ModelSummary",
    "ProviderError",
    "ProviderHealth",
    "RegistryError",
    "RoutingDecision",
    "RoutingRequest",
    "SCORE_WEIGHTS",
    "SimulatedProvider",
    "StreamChunk",
    "TASK_CAPABILITY_MAP",
    "TASK_MIN_CONTEXT",
    "UnsupportedModelError",
    "build_server_args",
    "encode_completion_request",
    "mimo_edge_pool",
    "new_model_id",
    "parse_completion_response",
    "parse_sse_event",
    "resolve_binary",
    "run_benchmark",
    "seed_mimo_edge_pool",
]
