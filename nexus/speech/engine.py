"""Speech engine (New Plan §19) — the facade over §19.1–§19.4.

One object wiring the §19.1 provider contract, the §19.2 engines
(sherpa-onnx / SAPI / null behind honest probes), the §19.4 pipeline
(Microphone → STT → Normalization → Intent → Task), the §19.3
benchmark and the §12 memory bridge.  The engine owns *speech
semantics only* — recognition engines stay replaceable adapters
(Plan §61), and the capability matrix it emits carries proven facts,
never invented ✅.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .benchmark import BenchmarkReport, SpeechBenchmark, load_fixture_cases
from .contracts import (
    BENCHMARK_CONDITIONS,
    PIPELINE_STAGES,
    AudioInput,
    LanguageDetection,
    SpeechProvider,
    TranscriptionResult,
)
from .intent import IntentRouter
from .pipeline import PipelineResult, VoicePipeline
from .providers import create_provider


class SpeechEngine:
    """The §19 facade — transcribe · detect · route · benchmark."""

    def __init__(
        self,
        provider: SpeechProvider | None = None,
        *,
        router: IntentRouter | None = None,
        memory_sink: Any = None,
        source: Any = None,
    ) -> None:
        self._provider = provider or create_provider()
        self._router = router or IntentRouter()
        self._pipeline = VoicePipeline(
            self._provider,
            router=self._router,
            source=source,
            memory_sink=memory_sink,
        )
        self._benchmark = SpeechBenchmark(self._provider, router=self._router)

    # ------------------------------------------------------------ §19.1

    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        return self._provider.transcribe(audio)

    def detect_language(self, audio: AudioInput) -> LanguageDetection:
        return self._provider.detect_language(audio)

    # ------------------------------------------------------------ §19.4

    def voice_task(self, audio: AudioInput | None = None) -> PipelineResult:
        """One utterance through all five stages — verdicts included."""
        return self._pipeline.run(audio)

    # ------------------------------------------------------------ §19.3

    def benchmark(
        self,
        fixtures_dir: str | Path | None = None,
    ) -> BenchmarkReport:
        """The six real conditions over this engine's provider."""
        cases = (
            load_fixture_cases(fixtures_dir) if fixtures_dir else load_fixture_cases()
        )
        return self._benchmark.run(cases)

    # ----------------------------------------------------------- matrix

    def describe(self) -> dict[str, Any]:
        """Capability-matrix rows — proven on this host, no invented ✅."""
        return {
            "engine": "nexus.speech",
            "provider": self._provider.describe(),
            "pipeline_stages": list(PIPELINE_STAGES),
            "benchmark_conditions": list(BENCHMARK_CONDITIONS),
        }

    def close(self) -> None:
        """Speech providers hold no file handles of their own (the SAPI
        temp file closes inside ``transcribe``; ONNX sessions are
        process-scoped) — this is the explicit, documented no-op."""
        return None
