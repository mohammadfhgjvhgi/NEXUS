"""Pipeline tests (§19.4) — five verbatim stages, verdicts, real memory."""

from __future__ import annotations

import pytest
from fixtures import ScriptedProvider, fixture_audio

from nexus.memory.engine import MemoryEngine
from nexus.memory.store import SQLiteMemoryStore
from nexus.speech.contracts import (
    PIPELINE_STAGES,
    ProviderUnavailableError,
    StageState,
)
from nexus.speech.memory import SpeechMemory
from nexus.speech.pipeline import (
    FileAudioSource,
    MicAudioSource,
    VoicePipeline,
)

_EN = "voice://fixture/en_basic"
_AR = "voice://fixture/ar_basic"


class TestStages:
    def test_stage_order_is_verbatim(self) -> None:
        provider = ScriptedProvider(
            responses={_EN: "Open the browser and run the tests"}
        )
        result = VoicePipeline(provider).run(fixture_audio("en_basic"))
        assert [t.name for t in result.traces] == list(PIPELINE_STAGES)
        assert result.ok

    def test_task_lands_with_fields(self) -> None:
        provider = ScriptedProvider(
            responses={_EN: "Open the browser and run the tests"}
        )
        result = VoicePipeline(provider).run(fixture_audio("en_basic"))
        task = result.task
        assert task is not None
        assert task.intent == "open_app"
        assert task.task_kind == "open_application"
        assert task.provider == "scripted"
        assert task.audio_uri == _EN
        assert task.argument == "the browser and run the tests"
        assert task.language == "en"

    def test_arabic_end_to_end(self) -> None:
        provider = ScriptedProvider(responses={_AR: "افتح المتصفح"})
        result = VoicePipeline(provider).run(fixture_audio("ar_basic"))
        assert result.task is not None
        assert result.task.intent == "open_app"
        assert result.task.argument == "المتصفح"

    def test_unknown_intent_still_lands_a_task(self) -> None:
        provider = ScriptedProvider(
            responses={_EN: "السماء الزرقاء اليوم جميلة"}, default=""
        )
        result = VoicePipeline(provider).run(fixture_audio("en_basic"))
        assert result.task is not None
        assert result.task.intent == "unknown"
        assert result.task.task_kind == "unclassified"
        assert result.ok  # unknown is a valid verdict, not a failure


class TestFailureTraces:
    def test_provider_failure_stops_at_stt(self) -> None:
        class Refusing(ScriptedProvider):
            def transcribe(self, audio):
                raise ProviderUnavailableError("engine gone")

        result = VoicePipeline(Refusing()).run(fixture_audio("en_basic"))
        assert result.task is None and not result.ok
        states = {t.name: t.state for t in result.traces}
        assert states["microphone"] == StageState.OK
        assert states["stt"] == StageState.FAILED
        assert states["normalization"] == StageState.PENDING
        assert states["task"] == StageState.PENDING

    def test_empty_transcript_is_a_failure_not_a_lie(self) -> None:
        provider = ScriptedProvider(responses={_EN: ""}, default="")
        result = VoicePipeline(provider).run(fixture_audio("en_basic"))
        assert not result.ok
        assert {t.name: t.state for t in result.traces}["stt"] == StageState.FAILED

    def test_no_utterance_and_no_source_refuses(self) -> None:
        result = VoicePipeline(ScriptedProvider()).run(None)
        assert {t.name: t.state for t in result.traces}["microphone"] == (
            StageState.FAILED
        )


class TestSources:
    def test_source_stage_used_when_no_audio_given(self) -> None:
        provider = ScriptedProvider(responses={_AR: "افتح المتصفح"})
        pipeline = VoicePipeline(provider, source=FileAudioSource(fixture_audio("ar_basic")))
        result = pipeline.run(None)
        assert result.ok and result.task is not None

    def test_mic_source_refuses_honestly(self) -> None:
        with pytest.raises(ProviderUnavailableError, match="microphone"):
            MicAudioSource().capture()


class TestMemoryBridge:
    def test_task_remembered_and_recalled_with_provenance(self, tmp_path) -> None:
        memory = MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem.sqlite")))
        try:
            sink = SpeechMemory(memory)
            provider = ScriptedProvider(responses={_EN: "Open the browser and run the tests"})
            pipeline = VoicePipeline(provider, memory_sink=sink)
            result = pipeline.run(fixture_audio("en_basic"))
            assert result.ok
            detail = [t for t in result.traces if t.name == "task"][0].detail
            assert "remembered" in detail

            hits = sink.recall("voice task", limit=5)
            assert hits, "the voice task must be recallable"
            fact = [h for h in hits if h["type"] == "fact"][0]
            assert "open_app" in fact["content"]
            assert fact["sources"], "provenance must ride the record"
            assert fact["sources"][0]["method"] == "user_statement"
            assert fact["sources"][0]["uri"] == _EN
        finally:
            memory.close()  # real-Windows law: close before temp cleanup

    def test_unknown_intent_is_not_remembered(self, tmp_path) -> None:
        memory = MemoryEngine(SQLiteMemoryStore(str(tmp_path / "mem2.sqlite")))
        try:
            sink = SpeechMemory(memory)
            provider = ScriptedProvider(responses={_EN: "كلام عادي بلا أمر"})
            result = VoicePipeline(provider, memory_sink=sink).run(fixture_audio("en_basic"))
            assert result.task is not None
            detail = [t for t in result.traces if t.name == "task"][0].detail
            assert "remembered" not in detail
            assert not sink.recall("voice task", limit=5)
        finally:
            memory.close()
