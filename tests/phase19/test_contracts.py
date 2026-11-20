"""§19.1 contract tests — the Speech API's laws."""

from __future__ import annotations

import pytest

from nexus.speech.contracts import (
    BENCHMARK_CONDITIONS,
    CONFIDENCE_UNREPORTED,
    INTENT_TO_TASK_KIND,
    PIPELINE_STAGES,
    AudioError,
    AudioInput,
    LanguageDetection,
    StageState,
    StageTrace,
    TranscriptionResult,
    VoiceTask,
)
from nexus.speech.providers import PROVIDER_NAMES


def _audio(samples=(0.1, -0.2, 0.3), rate=16000, uri="voice://test") -> AudioInput:
    return AudioInput(sample_rate_hz=rate, samples=tuple(samples), source_uri=uri)


class TestAudioInput:
    def test_duration_math(self) -> None:
        audio = _audio(samples=(0.0,) * 16000)
        assert audio.duration_seconds == pytest.approx(1.0)

    def test_empty_samples_refused(self) -> None:
        with pytest.raises(AudioError, match="empty"):
            AudioInput(sample_rate_hz=16000, samples=())

    def test_bad_rate_refused(self) -> None:
        with pytest.raises(AudioError, match="positive"):
            AudioInput(sample_rate_hz=0, samples=(0.1,))

    def test_honest_default_uri(self) -> None:
        audio = AudioInput(sample_rate_hz=16000, samples=(0.1,))
        assert audio.source_uri == "memory://audio"

    def test_as_dict_counts_samples(self) -> None:
        info = _audio().as_dict()
        assert info["samples"] == 3 and info["sample_rate_hz"] == 16000


class TestResults:
    def test_transcription_roundtrip(self) -> None:
        result = TranscriptionResult(
            text="hello", language="en", confidence=0.7, provider="x"
        )
        assert result.as_dict()["confidence"] == 0.7
        assert result.as_dict()["provider"] == "x"

    def test_confidence_unreported_is_never_zero(self) -> None:
        assert CONFIDENCE_UNREPORTED < 0.0

    def test_detection_documents_its_method(self) -> None:
        native = LanguageDetection(language="ar", method="native")
        inferred = LanguageDetection(language="en", method="script-inference")
        assert native.as_dict()["method"] == "native"
        assert inferred.as_dict()["method"] == "script-inference"


class TestVocabularies:
    def test_pipeline_stages_verbatim(self) -> None:
        assert PIPELINE_STAGES == (
            "microphone",
            "stt",
            "normalization",
            "intent",
            "task",
        )

    def test_benchmark_conditions_verbatim(self) -> None:
        assert BENCHMARK_CONDITIONS == (
            "arabic",
            "arabic-technical",
            "english",
            "mixed-arabic-english",
            "fast-speech",
            "noise",
        )

    def test_stage_trace_states(self) -> None:
        assert StageTrace("stt").state == StageState.PENDING
        assert StageTrace("stt", StageState.OK).as_dict()["state"] == "ok"


class TestVoiceTask:
    def test_task_kind_mapping_is_total(self) -> None:
        for intent in (
            "open_app",
            "run_command",
            "search_web",
            "create_note",
            "system_status",
            "stop",
            "unknown",
        ):
            assert intent in INTENT_TO_TASK_KIND

    def test_task_defaults_stamped(self) -> None:
        task = VoiceTask(
            utterance="افتح المتصفح",
            normalized_text="افتح المتصفح",
            language="ar",
            intent="open_app",
            confidence=0.5,
        )
        assert task.created_at  # stamped at construction
        # the raw task kind stays honest — the pipeline maps intent → kind
        assert task.task_kind == "unclassified"
        assert INTENT_TO_TASK_KIND["open_app"] == "open_application"
        assert task.as_dict()["utterance"] == "افتح المتصفح"


class TestRegistry:
    def test_provider_names(self) -> None:
        assert PROVIDER_NAMES == ("sherpa-onnx", "sapi", "null")
