"""Speech benchmark (New Plan §19.3) — six real conditions, honest math.

    Arabic · Arabic technical · English · Mixed Arabic-English ·
    Fast speech · Noise

The cases ride *real audio fixtures* (real neural speech, committed as
text-safe base64 — see ``tests/phase19/fixtures``): each case carries
its expected transcript and expected intent, and the report scores the
provider's hypothesis against them through the §19.4 normalizer + WER
scorer.  Nothing here passes or fails a provider on a curve — the
report states the numbers, the device gate decides.

Sandbox/CI note: the harness runs with any provider, including the
scripted test double — the numbers are then *provenance rows* for the
machinery, not engine claims.  The device proof runs the same harness
with the real provider and writes the verdict JSON.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import BENCHMARK_CONDITIONS, AudioInput, SpeechProvider, TranscriptionResult
from .intent import IntentRouter
from .wavio import load_wav
from .wer import word_error_rate

#: the fixtures directory shipped with tests/phase19
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "phase19" / "fixtures"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One §19.3 case — real audio, expected text, expected intent."""

    id: str
    language: str
    condition: str
    expected_text: str
    expected_intent: str
    audio: AudioInput
    generator: str = ""
    reference_transcript: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "language": self.language,
            "condition": self.condition,
            "expected_text": self.expected_text,
            "expected_intent": self.expected_intent,
            "generator": self.generator,
            "duration_seconds": round(self.audio.duration_seconds, 3),
        }


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One scored row — the provider's hypothesis against the truth."""

    case: BenchmarkCase
    hypothesis: str
    detected_language: str
    wer: float
    intent_predicted: str
    intent_confidence: float
    latency_seconds: float
    provider: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.id,
            "condition": self.case.condition,
            "language_expected": self.case.language,
            "language_detected": self.detected_language,
            "expected": self.case.expected_text,
            "hypothesis": self.hypothesis,
            "wer": round(self.wer, 4),
            "intent_expected": self.case.expected_intent,
            "intent_predicted": self.intent_predicted,
            "intent_confidence": round(self.intent_confidence, 4),
            "latency_seconds": round(self.latency_seconds, 4),
            "provider": self.provider,
        }


def load_fixture_cases(
    fixtures_dir: str | Path = FIXTURES_DIR,
) -> tuple[BenchmarkCase, ...]:
    """Real WAV bytes (base64-armored for the tunnel's text transport)
    + the manifest → the six §19.3 cases, in manifest order."""
    base = Path(fixtures_dir)
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    cases: list[BenchmarkCase] = []
    for row in manifest["fixtures"]:
        raw = base64.b64decode((base / row["file"]).read_text(encoding="ascii"))
        audio = load_wav(raw, source_uri=f"voice://fixture/{row['id']}")
        cases.append(
            BenchmarkCase(
                id=row["id"],
                language=row["language"],
                condition=row["condition"],
                expected_text=row["expected_text"],
                expected_intent=row["expected_intent"],
                audio=audio,
                generator=row.get("generator", ""),
                reference_transcript=row.get("whisper_tiny_reference_transcript", ""),
            )
        )
    return tuple(cases)


class SpeechBenchmark:
    """The §19.3 harness — six conditions over one provider."""

    conditions: tuple[str, ...] = BENCHMARK_CONDITIONS

    def __init__(
        self,
        provider: SpeechProvider,
        *,
        router: IntentRouter | None = None,
    ) -> None:
        self._provider = provider
        self._router = router or IntentRouter()

    def run_case(self, case: BenchmarkCase) -> CaseResult:
        result: TranscriptionResult = self._provider.transcribe(case.audio)
        hypothesis = result.text
        wer = word_error_rate(case.expected_text, hypothesis)
        verdict = self._router.route(hypothesis)
        return CaseResult(
            case=case,
            hypothesis=hypothesis,
            detected_language=result.language,
            wer=wer,
            intent_predicted=verdict.intent,
            intent_confidence=verdict.confidence,
            latency_seconds=result.latency_seconds,
            provider=result.provider or self._provider.name,
        )

    def run(self, cases: tuple[BenchmarkCase, ...]) -> BenchmarkReport:
        rows = [self.run_case(case) for case in cases]
        return BenchmarkReport(rows=tuple(rows), provider=self._provider.name)


class BenchmarkReport:
    """Aggregated §19.3 numbers — stated, not judged."""

    def __init__(
        self,
        rows: tuple[CaseResult, ...],
        *,
        provider: str = "",
    ) -> None:
        self.rows = rows
        self.provider = provider

    @property
    def mean_wer(self) -> float:
        if not self.rows:
            return 0.0
        return sum(r.wer for r in self.rows) / len(self.rows)

    @property
    def intent_accuracy(self) -> float:
        """Predicted intents matching expectation, unknowns counting as
        misses — the router is part of the system under test."""
        if not self.rows:
            return 0.0
        hits = sum(
            1
            for r in self.rows
            if r.intent_predicted == r.case.expected_intent
        )
        return hits / len(self.rows)

    def by_condition(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for row in self.rows:
            out.setdefault(row.case.condition, row.wer)
        return {k: round(v, 4) for k, v in out.items()}

    def as_dict(self) -> dict[str, Any]:
        nonempty = sum(1 for r in self.rows if r.hypothesis.strip())
        return {
            "provider": self.provider,
            "conditions": list(BENCHMARK_CONDITIONS),
            "cases": [r.as_dict() for r in self.rows],
            "summary": {
                "cases": len(self.rows),
                "mean_wer": round(self.mean_wer, 4),
                "intent_accuracy": round(self.intent_accuracy, 4),
                "by_condition_wer": self.by_condition(),
                "transcripts_nonempty": nonempty,
            },
        }
