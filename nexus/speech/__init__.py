"""NEXUS Speech System (New Plan §19) — *local voice control*.

* ``contracts``   — the §19.1 Speech API (``SpeechProvider`` ·
                    ``transcribe`` · ``detect_language``), the §19.4
                    pipeline stages and the §19.3 conditions, verbatim;
* ``wavio``       — the stdlib WAV floor (parse · write · rms), honest
                    refusal for what it cannot understand;
* ``textnorm``    — the §19.4 Normalization stage (Arabic · English ·
                    mixed, one law per token);
* ``wer``         — the §19.3 scorer (WER/CER over normalized forms);
* ``providers``   — the §19.2 engines behind one contract:
                    sherpa-onnx (MODE A when installed + model), the
                    Windows SAPI floor (MODE A, zero installs) and the
                    honest null refusal;
* ``intent``      — the §19.4 Intent stage (bilingual rules, honest
                    unknown);
* ``pipeline``    — Microphone → STT → Normalization → Intent → Task,
                    a verdict per stage;
* ``memory``      — the §12 bridge: voice tasks remembered with their
                    provenance;
* ``benchmark``   — the §19.3 six-condition harness over real audio
                    fixtures;
* ``engine``      — the facade.

The Core stays stdlib-only: recognition engines enter behind the
provider contract, probed honestly, never assumed.
"""

from .benchmark import (
    BenchmarkCase,
    BenchmarkReport,
    SpeechBenchmark,
    load_fixture_cases,
)
from .contracts import (
    BENCHMARK_CONDITIONS,
    CONFIDENCE_UNREPORTED,
    PIPELINE_STAGES,
    AudioError,
    AudioInput,
    LanguageDetection,
    ProviderUnavailableError,
    SpeechError,
    SpeechProvider,
    StageState,
    StageTrace,
    TranscriptionError,
    TranscriptionResult,
    VoiceTask,
)
from .engine import SpeechEngine
from .intent import (
    INTENTS,
    IntentResult,
    IntentRouter,
    IntentRule,
)
from .pipeline import FileAudioSource, MicAudioSource, PipelineResult, VoicePipeline
from .providers import PROVIDER_NAMES, available_providers, create_provider
from .textnorm import detect_script, normalize_text
from .wavio import load_wav, rms, wav_bytes, write_wav
from .wer import accuracy, character_error_rate, word_error_rate

__all__ = [
    "AudioError",
    "AudioInput",
    "BENCHMARK_CONDITIONS",
    "BenchmarkCase",
    "BenchmarkReport",
    "CONFIDENCE_UNREPORTED",
    "FileAudioSource",
    "INTENTS",
    "IntentResult",
    "IntentRouter",
    "IntentRule",
    "LanguageDetection",
    "MicAudioSource",
    "PROVIDER_NAMES",
    "PIPELINE_STAGES",
    "PipelineResult",
    "ProviderUnavailableError",
    "SpeechBenchmark",
    "SpeechEngine",
    "SpeechError",
    "SpeechProvider",
    "StageState",
    "StageTrace",
    "TranscriptionError",
    "TranscriptionResult",
    "VoicePipeline",
    "VoiceTask",
    "accuracy",
    "available_providers",
    "character_error_rate",
    "create_provider",
    "detect_script",
    "load_fixture_cases",
    "load_wav",
    "normalize_text",
    "rms",
    "wav_bytes",
    "word_error_rate",
    "write_wav",
]
