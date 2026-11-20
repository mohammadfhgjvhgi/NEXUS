"""Provider tests (§19.1/§19.2) — honest probes, real seams, real floor."""

from __future__ import annotations

import sys

import pytest
from fixtures import ScriptedProvider, fixture_audio

from nexus.speech.contracts import (
    ProviderUnavailableError,
    SpeechProvider,
    TranscriptionResult,
)
from nexus.speech.providers import available_providers, create_provider
from nexus.speech.providers.null import NullProvider
from nexus.speech.providers.sapi import SapiProvider, sapi_available
from nexus.speech.providers.sherpa import (
    SHERPA_ONNX_PIN,
    SherpaModelConfig,
    SherpaOnnxProvider,
    sherpa_available,
)


class _FakeStream:
    def __init__(self, text: str, lang: str) -> None:
        self._text, self._lang = text, lang
        self.result = None

    def accept_waveform(self, rate: int, samples: object) -> None:
        self.rate, self.samples = rate, samples

    def compute(self) -> None:  # the engine's own name for decoding
        pass


class _FakeRecognizer:
    """The injected engine — MODE A direct use without a 140 MB model."""

    def __init__(self, text: str = "افتح المتصفح", lang: str = "ar") -> None:
        self._text, self._lang = text, lang
        self.streams: list[_FakeStream] = []

    def create_stream(self) -> _FakeStream:
        stream = _FakeStream(self._text, self._lang)
        self.streams.append(stream)
        return stream

    def decode_stream(self, stream: _FakeStream) -> None:
        stream.result = type("R", (), {"text": self._text, "lang": self._lang})()


class TestContract:
    def test_providers_are_speech_providers(self) -> None:
        for provider in (NullProvider(), SapiProvider(), SherpaOnnxProvider()):
            assert isinstance(provider, SpeechProvider)

    def test_null_refuses_transcribe(self) -> None:
        with pytest.raises(ProviderUnavailableError, match="no speech provider"):
            NullProvider().transcribe(fixture_audio("en_basic"))

    def test_null_refuses_detection(self) -> None:
        with pytest.raises(ProviderUnavailableError, match="no speech provider"):
            NullProvider().detect_language(fixture_audio("en_basic"))

    def test_null_matrix_is_honest(self) -> None:
        row = NullProvider().describe()
        assert row["installed"] == "False"
        assert "sherpa-onnx" in row["detail"]


class TestSherpaProbe:
    def test_pin_is_bounded(self) -> None:
        assert SHERPA_ONNX_PIN == "sherpa-onnx>=1.10,<2"

    def test_probe_is_truthful_here(self) -> None:
        row = sherpa_available()
        data = row.as_dict()
        assert data["installed"] in ("True", "False")
        if row.installed and not row.model_found:
            assert "NEXUS_SPEECH_MODEL_DIR" in row.detail

    def test_transcribe_without_model_refuses(self) -> None:
        provider = SherpaOnnxProvider(
            model=SherpaModelConfig(encoder="x", decoder="y", tokens="z")
        )
        with pytest.raises(ProviderUnavailableError):
            provider.transcribe(fixture_audio("en_basic"))

    def test_injected_engine_direct_use(self) -> None:
        engine = _FakeRecognizer(text="افتح المتصفح", lang="ar")
        provider = SherpaOnnxProvider(recognizer_factory=lambda: engine)
        result = provider.transcribe(fixture_audio("ar_basic"))
        assert isinstance(result, TranscriptionResult)
        assert result.text == "افتح المتصفح"
        assert result.language == "ar"
        assert result.provider == "sherpa-onnx"
        assert result.confidence == -1.0  # whisper reports none — honest
        # the waveform really flowed into the engine
        assert engine.streams[0].rate == 16000

    def test_injected_native_detection(self) -> None:
        provider = SherpaOnnxProvider(
            recognizer_factory=lambda: _FakeRecognizer(
                text="Open the browser", lang="en"
            )
        )
        detection = provider.detect_language(fixture_audio("en_basic"))
        assert detection.language == "en"
        assert detection.method == "native"

    def test_configured_language_is_reported_as_configured(self) -> None:
        config = SherpaModelConfig(
            encoder="e", decoder="d", tokens="t", language="ar"
        )
        provider = SherpaOnnxProvider(
            model=config, recognizer_factory=_FakeRecognizer
        )
        detection = provider.detect_language(fixture_audio("ar_basic"))
        assert detection.method == "configured"
        assert detection.language == "ar"


class TestSapiProbe:
    def test_off_windows_refuses_honestly(self) -> None:
        row = sapi_available()
        if sys.platform == "win32":
            assert row.recognizer_count >= 0  # probe ran for real
        else:
            assert row.installed is False
            assert "Windows" in row.detail

    def test_transcribe_off_windows_refuses(self) -> None:
        if sys.platform == "win32":
            pytest.skip("this assertion targets non-Windows hosts")
        with pytest.raises(ProviderUnavailableError, match="SAPI"):
            SapiProvider().transcribe(fixture_audio("en_basic"))


class TestSelection:
    def test_auto_select_returns_a_real_name(self) -> None:
        provider = create_provider()
        assert provider.name in ("sherpa-onnx", "sapi", "null")
        assert provider.describe()

    def test_unknown_name_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown provider"):
            create_provider(preferred="skynet")

    def test_matrix_rows_cover_all_engines(self) -> None:
        rows = available_providers()
        assert {row["provider"] for row in rows} == {
            "sherpa-onnx",
            "sapi",
            "null",
        }


class TestScriptedDouble:
    def test_labelled_and_deterministic(self) -> None:
        double = ScriptedProvider(
            responses={"voice://fixture/en_basic": "Open the browser and run the tests"}
        )
        result = double.transcribe(fixture_audio("en_basic"))
        assert result.provider == "scripted"
        assert result.text == "Open the browser and run the tests"
        assert result.language == "en"
        assert double.calls == ["voice://fixture/en_basic"]

    def test_detection_refuses_without_text(self) -> None:
        double = ScriptedProvider(default="")
        with pytest.raises(ProviderUnavailableError):
            double.detect_language(fixture_audio("en_basic"))
