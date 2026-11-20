"""Speech-system contracts (New Plan §19.1–§19.4).

Vocabularies verbatim from the plan:

§19.1 — the Speech API::

    SpeechProvider
    transcribe
    detect_language

§19.3 — the benchmark conditions::

    Arabic   Arabic technical   English   Mixed Arabic-English
    Fast speech   Noise

§19.4 — the pipeline, verbatim and ordered::

    Microphone → STT → Normalization → Intent → Task

NEXUS owns the speech semantics (Plan §61's law): every recognition
engine — sherpa-onnx (§19.2, MODE A when installed, MODE B behind the
NEXUS :class:`SpeechProvider` contract) or the Windows built-in SAPI
dictation (MODE A with zero installs) — enters behind one contract;
the pipeline never sees a vendor type.  When no engine exists the
providers say so honestly (:class:`ProviderUnavailableError`) —
availability is probed, never assumed, and no capability row is
invented without proof.

عقود نظام الصوت — SpeechProvider وtranscribe وdetect_language حرفية،
شروط المعيار الستة، ومراحل السير الخمس كما في الخطة.

Stdlib only (recognition engines are optional extras).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ----------------------------------------------------------------- errors


class SpeechError(Exception):
    """Speech-engine misuse or operation failure."""


class AudioError(SpeechError):
    """The audio bytes could not be understood — never silently guessed."""


class ProviderUnavailableError(SpeechError):
    """No usable recognition engine on this host — the honest refusal."""


class TranscriptionError(SpeechError):
    """The engine ran but produced no usable transcription."""


# --------------------------------------------------------------- helpers


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds (house format)."""
    return datetime.now(UTC).isoformat()


#: A provider that cannot measure confidence reports this — never 0.0,
#: which would read as a real «confidently wrong» score.
CONFIDENCE_UNREPORTED = -1.0


# ------------------------------------------------------------ §19.4 stages


#: §19.4 — the pipeline stages, verbatim and ordered.
PIPELINE_STAGES: tuple[str, ...] = (
    "microphone",
    "stt",
    "normalization",
    "intent",
    "task",
)


class StageState:
    """A stage verdict — pending / ok / failed / skipped."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class StageTrace:
    """One §19.4 stage's outcome — name, state, an honest detail line."""

    name: str
    state: str = StageState.PENDING
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "state": self.state, "detail": self.detail}


# ---------------------------------------------------------- §19.3 conditions


#: §19.3 — the six benchmark conditions, verbatim from the plan.
BENCHMARK_CONDITIONS: tuple[str, ...] = (
    "arabic",
    "arabic-technical",
    "english",
    "mixed-arabic-english",
    "fast-speech",
    "noise",
)


# ------------------------------------------------------------------ audio


@dataclass(frozen=True, slots=True)
class AudioInput:
    """One utterance entering the engine — mono samples plus provenance.

    ``samples`` are floats in ``[-1.0, 1.0]`` at ``sample_rate_hz``;
    ``source_uri`` is the honest location (``voice://fixture/...`` or a
    real ``file://`` path — a bare name must not fake a file location).
    """

    sample_rate_hz: int
    samples: tuple[float, ...]
    source_uri: str = ""

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise AudioError(f"sample rate must be positive, got {self.sample_rate_hz}")
        if not self.samples:
            raise AudioError("audio input is empty — no samples")
        if self.source_uri == "":
            object.__setattr__(self, "source_uri", "memory://audio")

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / float(self.sample_rate_hz)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "samples": len(self.samples),
            "duration_seconds": round(self.duration_seconds, 4),
            "source_uri": self.source_uri,
        }


# ------------------------------------------------------------ §19.1 results


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """The ``transcribe`` verb's product — text, language, confidence.

    ``confidence`` is the engine's own score when it has one (SAPI
    does; whisper does not) and :data:`CONFIDENCE_UNREPORTED` when the
    provider reports none — the matrix never invents a number.
    """

    text: str
    language: str = ""
    confidence: float = CONFIDENCE_UNREPORTED
    provider: str = ""
    latency_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "language": self.language,
            "confidence": self.confidence,
            "provider": self.provider,
            "latency_seconds": round(self.latency_seconds, 4),
        }


@dataclass(frozen=True, slots=True)
class LanguageDetection:
    """The ``detect_language`` verb's product — a code and its method.

    ``method`` documents *how* the code was obtained: ``native`` (the
    engine reports it — whisper's language token), ``script-inference``
    (unicode ranges over the transcript) or ``configured`` (the engine
    was pinned to one language at load).
    """

    language: str
    confidence: float = CONFIDENCE_UNREPORTED
    method: str = "native"
    provider: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "confidence": self.confidence,
            "method": self.method,
            "provider": self.provider,
        }


class SpeechProvider(ABC):
    """One §19.1 recognition engine behind the NEXUS contract.

    ``name`` is a stable id (reports, capability matrix).  ``transcribe``
    and ``detect_language`` return honest results or raise honestly:
    :class:`ProviderUnavailableError` when the engine is not usable on
    this host, :class:`TranscriptionError` when it ran but produced
    nothing.
    """

    name: str

    @abstractmethod
    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        """One utterance → text — honest output or an honest raise."""

    @abstractmethod
    def detect_language(self, audio: AudioInput) -> LanguageDetection:
        """One utterance → a language code and how it was obtained."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Capability-matrix rows — proven facts only, no invented ✅."""


# ------------------------------------------------------------- §19.4 task


#: intent → NEXUS task kind (the §19.4 *Task* landing).
INTENT_TO_TASK_KIND: dict[str, str] = {
    "open_app": "open_application",
    "run_command": "run_command",
    "search_web": "web_search",
    "create_note": "create_note",
    "system_status": "system_status",
    "stop": "stop_task",
    "unknown": "unclassified",
}


@dataclass(frozen=True, slots=True)
class VoiceTask:
    """The pipeline's product — one utterance turned into a NEXUS task."""

    utterance: str
    normalized_text: str
    language: str
    intent: str
    confidence: float
    argument: str = ""
    task_kind: str = "unclassified"
    provider: str = ""
    audio_uri: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "utterance": self.utterance,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "intent": self.intent,
            "confidence": self.confidence,
            "argument": self.argument,
            "task_kind": self.task_kind,
            "provider": self.provider,
            "audio_uri": self.audio_uri,
            "created_at": self.created_at,
        }
