"""Benchmark tests (§19.3) — six real conditions, deterministic math."""

from __future__ import annotations

import pytest
from fixtures import ScriptedProvider, manifest_rows

from nexus.speech.benchmark import (
    SpeechBenchmark,
    load_fixture_cases,
)
from nexus.speech.contracts import BENCHMARK_CONDITIONS


@pytest.fixture()
def cases():
    return load_fixture_cases()


@pytest.fixture()
def scripted_report(cases):
    """The double returns each case's whisper-tiny reference transcript —
    the manifest makes every WER row deterministic."""
    responses = {
        f"voice://fixture/{row['id']}": row["whisper_tiny_reference_transcript"]
        for row in manifest_rows()
    }
    return SpeechBenchmark(ScriptedProvider(responses)).run(cases)


class TestFixtureLoading:
    def test_six_real_cases(self, cases) -> None:
        assert [c.id for c in cases] == [row["id"] for row in manifest_rows()]
        assert {c.condition for c in cases} == set(BENCHMARK_CONDITIONS)

    def test_every_case_has_real_audio_and_expectations(self, cases) -> None:
        for case in cases:
            assert case.audio.duration_seconds > 0.5
            assert case.expected_text.strip()
            assert case.expected_intent
            assert case.reference_transcript, case.id

    def test_languages_cover_the_spec(self, cases) -> None:
        languages = {c.language for c in cases}
        assert languages == {"ar", "en", "mixed"}


class TestScoring:
    def test_english_reference_transcribes_perfectly(self, scripted_report) -> None:
        rows = {r.case.id: r for r in scripted_report.rows}
        assert rows["en_basic"].wer == 0.0
        assert rows["fast"].wer == 0.0

    def test_arabic_rows_are_real_and_finite(self, scripted_report) -> None:
        rows = {r.case.id: r for r in scripted_report.rows}
        # whisper-tiny mishears some Arabic words — never zero, never wild
        assert 0.1 <= rows["ar_basic"].wer <= 1.0
        assert 0.1 <= rows["ar_tech"].wer <= 1.0

    def test_noise_degrades_honestly(self, scripted_report) -> None:
        rows = {r.case.id: r for r in scripted_report.rows}
        assert rows["noise"].wer >= 0.9

    def test_intent_rows_match_the_router_law(self, scripted_report) -> None:
        rows = {r.case.id: r for r in scripted_report.rows}
        assert rows["ar_basic"].intent_predicted == "open_app"
        assert rows["ar_tech"].intent_predicted == "run_command"
        assert rows["en_basic"].intent_predicted == "open_app"
        assert rows["fast"].intent_predicted == "run_command"
        assert rows["mixed"].intent_predicted == "open_app"
        assert rows["noise"].intent_predicted == "unknown"
        assert scripted_report.intent_accuracy == pytest.approx(5 / 6)

    def test_report_summary_is_json_shaped(self, scripted_report) -> None:
        data = scripted_report.as_dict()
        assert data["provider"] == "scripted"
        assert len(data["cases"]) == 6
        summary = data["summary"]
        assert summary["cases"] == 6
        assert 0.0 <= summary["mean_wer"] <= 2.0
        assert set(summary["by_condition_wer"]) == set(BENCHMARK_CONDITIONS)
        assert summary["transcripts_nonempty"] == 6

    def test_latency_and_language_flow_through(self, scripted_report) -> None:
        rows = {r.case.id: r for r in scripted_report.rows}
        assert rows["ar_basic"].detected_language == "ar"
        assert rows["en_basic"].detected_language == "en"
        assert all(r.latency_seconds >= 0 for r in scripted_report.rows)
