"""Engine facade tests (§19) — wiring, matrix, identity."""

from __future__ import annotations

from fixtures import ScriptedProvider, fixture_audio, manifest_rows

from nexus.speech.benchmark import load_fixture_cases
from nexus.speech.engine import SpeechEngine
from nexus.speech.providers.null import NullProvider

_EN = "voice://fixture/en_basic"


class TestFacade:
    def test_transcribe_passthrough(self) -> None:
        engine = SpeechEngine(
            ScriptedProvider(responses={_EN: "Open the browser and run the tests"})
        )
        result = engine.transcribe(fixture_audio("en_basic"))
        assert result.text == "Open the browser and run the tests"
        engine.close()

    def test_detect_language_passthrough(self) -> None:
        engine = SpeechEngine(ScriptedProvider(responses={_EN: "Open it"}))
        detection = engine.detect_language(fixture_audio("en_basic"))
        assert detection.language == "en"
        assert detection.method == "script-inference"

    def test_voice_task_via_facade(self) -> None:
        engine = SpeechEngine(
            ScriptedProvider(responses={_EN: "Run the full system check now"})
        )
        result = engine.voice_task(fixture_audio("en_basic"))
        assert result.ok
        assert result.task is not None
        assert result.task.task_kind == "run_command"

    def test_benchmark_via_facade(self) -> None:
        responses = {
            f"voice://fixture/{row['id']}": row["whisper_tiny_reference_transcript"]
            for row in manifest_rows()
        }
        engine = SpeechEngine(ScriptedProvider(responses))
        report = engine.benchmark()
        assert len(report.rows) == 6
        assert report.mean_wer >= 0.0

    def test_describe_matrix_is_proven_shaped(self) -> None:
        engine = SpeechEngine(NullProvider())
        row = engine.describe()
        assert row["engine"] == "nexus.speech"
        assert row["pipeline_stages"] == [
            "microphone",
            "stt",
            "normalization",
            "intent",
            "task",
        ]
        assert len(row["benchmark_conditions"]) == 6
        assert row["provider"]["provider"] == "null"

    def test_default_provider_is_the_honest_floor_here(self) -> None:
        # in the sandbox/CI (no model, no Windows) the auto-selector must
        # land on the refusal floor — never a fake engine
        engine = SpeechEngine(NullProvider())
        assert engine.describe()["provider"]["provider"] == "null"


class TestIdentity:
    def test_phase_identity_is_at_least_19(self) -> None:
        import nexus

        # floor style: later phases bump the version without breaking this
        major, minor, _ = (int(p) for p in nexus.__version__.split("."))
        assert (major, minor) >= (0, 19), nexus.__version__
        assert nexus.NEXUS_PHASE >= 19

    def test_fixtures_load_from_the_installed_tree(self) -> None:
        cases = load_fixture_cases()
        assert len(cases) == 6
