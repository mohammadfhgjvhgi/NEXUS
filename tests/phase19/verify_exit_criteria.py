#!/usr/bin/env python3
"""Phase 19 verification harness — New Plan §19 Exit Gate.

Proves the Speech System section by section:

* A — Speech API (§19.1): the verbatim vocabulary — SpeechProvider ·
      transcribe · detect_language — the audio/results contracts, the
      honest refusals and the unreported-confidence law.
* B — sherpa-onnx (§19.2): the documented pin, the honest probe
      (engine? model? — never assumed), MODE A direct use through the
      NEXUS contract (injected engine), the null refusal floor, and
      the real engine end-to-end when the host actually has one.
* C — Benchmark (§19.3): the six real conditions over real audio
      fixtures — Arabic · Arabic technical · English · mixed
      Arabic-English · fast speech · noise — deterministic WER math
      and the intent verdicts.
* D — Pipeline (§19.4): the five stages verbatim and in order
      (Microphone → STT → Normalization → Intent → Task), a verdict
      per stage, honest failure traces, a voice task landed and
      remembered into a real §12 engine with its provenance.
* E — Honesty: probes that never invent availability (off-Windows
      SAPI, engine-without-model sherpa), an auto-selector that lands
      on the refusal floor when nothing exists, a capability matrix
      of proven rows only.
* F — Integration + regression: NEXUS_PHASE ≥ 19, nexus-core ≥
      0.19.0, the speech core stays stdlib-only at module top level,
      and the neighbor phase suites (15 · 16 · 17 · 18) stay green
      (skippable with --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, fn: Any) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        FAILED.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {label} — {type(exc).__name__}: {exc}")
    else:
        PASSED.append(label)
        print(f"  ✓ {label}")


def expects(exc_types: tuple[type, ...] | type, fn: Any, *args: Any, **kwargs: Any) -> None:
    try:
        fn(*args, **kwargs)
    except exc_types:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_types}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exc_types}, nothing raised")


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.speech.contracts import (
        BENCHMARK_CONDITIONS,
        CONFIDENCE_UNREPORTED,
        PIPELINE_STAGES,
        AudioError,
        AudioInput,
        LanguageDetection,
        SpeechProvider,
        TranscriptionResult,
    )
    from nexus.speech.providers.null import NullProvider

    def vocabulary_verbatim() -> None:
        assert PIPELINE_STAGES == ("microphone", "stt", "normalization", "intent", "task")
        assert BENCHMARK_CONDITIONS == (
            "arabic", "arabic-technical", "english",
            "mixed-arabic-english", "fast-speech", "noise",
        )

    def audio_laws() -> None:
        audio = AudioInput(sample_rate_hz=16000, samples=(0.0,) * 16000,
                           source_uri="voice://gate")
        assert audio.duration_seconds == 1.0
        expects((AudioError,), AudioInput, sample_rate_hz=16000, samples=())
        expects((AudioError,), AudioInput, sample_rate_hz=0, samples=(0.1,))

    def results_laws() -> None:
        result = TranscriptionResult(text="x", provider="p")
        assert result.confidence == CONFIDENCE_UNREPORTED < 0.0
        detection = LanguageDetection(language="ar", method="native")
        assert detection.as_dict()["method"] == "native"

    def provider_is_abstract() -> None:
        expects((TypeError,), SpeechProvider)  # abstract — no silent fake

    def task_mapping_total() -> None:
        from nexus.speech.contracts import INTENT_TO_TASK_KIND

        for intent in ("open_app", "run_command", "search_web",
                       "create_note", "system_status", "stop", "unknown"):
            assert intent in INTENT_TO_TASK_KIND

    def null_refuses() -> None:
        from nexus.speech.contracts import ProviderUnavailableError

        provider = NullProvider()
        expects((ProviderUnavailableError,), provider.transcribe, None)
        expects((ProviderUnavailableError,), provider.detect_language, None)

    check("A·vocabulary verbatim (stages + conditions)", vocabulary_verbatim)
    check("A·audio laws (duration · empty · rate)", audio_laws)
    check("A·results laws (confidence unreported · method)", results_laws)
    check("A·SpeechProvider is abstract", provider_is_abstract)
    check("A·VoiceTask shape stable", task_mapping_total)
    check("A·null provider refuses both verbs", null_refuses)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.speech.contracts import (
        CONFIDENCE_UNREPORTED,
        ProviderUnavailableError,
        TranscriptionResult,
    )
    from nexus.speech.providers.sherpa import (
        SHERPA_ONNX_PIN,
        SherpaModelConfig,
        SherpaOnnxProvider,
        sherpa_available,
    )

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fixtures import fixture_audio  # noqa: PLC0415 — gate-local

    def pin_documented() -> None:
        assert SHERPA_ONNX_PIN == "sherpa-onnx>=1.10,<2"

    def probe_truthful() -> None:
        row = sherpa_available()
        assert isinstance(row.installed, bool)
        if row.installed and not row.model_found:
            assert "NEXUS_SPEECH_MODEL_DIR" in row.detail
        if not row.installed:
            assert "pip install" in row.detail

    def missing_model_refuses() -> None:
        provider = SherpaOnnxProvider(
            model=SherpaModelConfig(encoder="missing-e", decoder="missing-d",
                                    tokens="missing-t")
        )
        expects((ProviderUnavailableError,), provider.transcribe, fixture_audio("en_basic"))

    class _FakeStream:
        def __init__(self) -> None:
            self.result: Any = None

        def accept_waveform(self, rate: int, samples: Any) -> None:
            self.rate, self.samples = rate, samples

    class _FakeRecognizer:
        def __init__(self) -> None:
            self.streams: list[_FakeStream] = []

        def create_stream(self) -> _FakeStream:
            stream = _FakeStream()
            self.streams.append(stream)
            return stream

        def decode_stream(self, stream: _FakeStream) -> None:
            stream.result = type("R", (), {"text": "افتح المتصفح", "lang": "ar"})()

    def mode_a_direct_use() -> None:
        engine = _FakeRecognizer()
        provider = SherpaOnnxProvider(recognizer_factory=lambda: engine)
        result = provider.transcribe(fixture_audio("ar_basic"))
        assert isinstance(result, TranscriptionResult)
        assert result.text == "افتح المتصفح" and result.language == "ar"
        assert result.confidence == CONFIDENCE_UNREPORTED
        assert engine.streams[0].rate == 16000  # the waveform really flowed
        detection = provider.detect_language(fixture_audio("ar_basic"))
        assert detection.method == "native"

    def real_engine_end_to_end_when_present() -> None:
        row = sherpa_available()
        if not (row.installed and row.model_found):
            print("    (host has no whisper model — the injected proof stands)")
            return
        provider = SherpaOnnxProvider()
        result = provider.transcribe(fixture_audio("en_basic"))
        assert result.text.strip() and result.language == "en"
        print(f"    (real engine: {result.text!r} lang={result.language})")

    check("B·pin documented and bounded", pin_documented)
    check("B·probe truthful (engine + model)", probe_truthful)
    check("B·missing model refuses honestly", missing_model_refuses)
    check("B·MODE A direct use via injected engine", mode_a_direct_use)
    check("B·real engine end-to-end when present", real_engine_end_to_end_when_present)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from fixtures import ScriptedProvider, manifest_rows  # noqa: PLC0415 — gate-local

    from nexus.speech.benchmark import SpeechBenchmark, load_fixture_cases
    from nexus.speech.contracts import BENCHMARK_CONDITIONS

    def six_real_cases() -> None:
        cases = load_fixture_cases()
        assert len(cases) == 6
        assert {c.condition for c in cases} == set(BENCHMARK_CONDITIONS)
        for case in cases:
            assert case.audio.duration_seconds > 0.5
            assert case.reference_transcript, case.id

    def scripted_report_is_deterministic() -> None:
        responses = {
            f"voice://fixture/{row['id']}": row["whisper_tiny_reference_transcript"]
            for row in manifest_rows()
        }
        report = SpeechBenchmark(ScriptedProvider(responses)).run(load_fixture_cases())
        rows = {r.case.id: r for r in report.rows}
        assert rows["en_basic"].wer == 0.0 and rows["fast"].wer == 0.0
        assert rows["noise"].wer >= 0.9
        assert report.intent_accuracy == 5 / 6
        summary = report.as_dict()["summary"]
        assert set(summary["by_condition_wer"]) == set(BENCHMARK_CONDITIONS)

    check("C·six real conditions over real audio", six_real_cases)
    check("C·deterministic WER + intent math", scripted_report_is_deterministic)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from fixtures import ScriptedProvider, fixture_audio  # noqa: PLC0415 — gate-local

    from nexus.memory.engine import MemoryEngine
    from nexus.memory.store import SQLiteMemoryStore
    from nexus.speech.contracts import PIPELINE_STAGES, ProviderUnavailableError, StageState
    from nexus.speech.memory import SpeechMemory
    from nexus.speech.pipeline import MicAudioSource, VoicePipeline

    def stages_verbatim_and_task() -> None:
        provider = ScriptedProvider(
            responses={"voice://fixture/en_basic": "Open the browser and run the tests"}
        )
        result = VoicePipeline(provider).run(fixture_audio("en_basic"))
        assert [t.name for t in result.traces] == list(PIPELINE_STAGES)
        assert result.ok
        task = result.task
        assert task is not None
        assert (task.intent, task.task_kind) == ("open_app", "open_application")
        assert task.argument.startswith("the browser")

    def failure_traces_honest() -> None:
        class Refusing(ScriptedProvider):
            def transcribe(self, audio: Any) -> Any:
                raise RuntimeError("engine gone")

        result = VoicePipeline(Refusing()).run(fixture_audio("en_basic"))
        assert not result.ok and result.task is None
        states = {t.name: t.state for t in result.traces}
        assert states["microphone"] == StageState.OK
        assert states["stt"] == StageState.FAILED
        assert states["task"] == StageState.PENDING

    def mic_refuses_honestly() -> None:
        expects((ProviderUnavailableError,), MicAudioSource().capture)

    def memory_roundtrip_with_provenance() -> None:
        with tempfile.TemporaryDirectory() as raw:
            memory = MemoryEngine(SQLiteMemoryStore(str(Path(raw) / "m.sqlite")))
            try:
                sink = SpeechMemory(memory)
                provider = ScriptedProvider(
                    responses={"voice://fixture/en_basic": "Open the browser"}
                )
                result = VoicePipeline(provider, memory_sink=sink).run(
                    fixture_audio("en_basic")
                )
                assert result.ok
                hits = sink.recall("voice task", limit=5)
                assert hits
                fact = [h for h in hits if h["type"] == "fact"][0]
                assert fact["sources"][0]["method"] == "user_statement"
                assert fact["sources"][0]["uri"] == "voice://fixture/en_basic"
            finally:
                memory.close()  # real-Windows law (WinError 32)

    check("D·five stages verbatim → task lands", stages_verbatim_and_task)
    check("D·failure stops with honest traces", failure_traces_honest)
    check("D·mic source refuses honestly", mic_refuses_honestly)
    check("D·voice task remembered into §12 with provenance",
          memory_roundtrip_with_provenance)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from nexus.speech.providers import available_providers, create_provider
    from nexus.speech.providers.sapi import sapi_available

    def matrix_rows_proven() -> None:
        by = {r["provider"]: r for r in available_providers()}
        assert set(by) == {"sherpa-onnx", "sapi", "null"}
        assert by["null"]["installed"] == "False"

    def sapi_probe_honest_here() -> None:
        row = sapi_available()
        assert isinstance(row.installed, bool)
        if not row.installed:
            assert row.detail  # the reason is always stated

    def auto_selector_lands_somewhere_real() -> None:
        provider = create_provider()
        assert provider.name in ("sherpa-onnx", "sapi", "null")
        assert provider.describe()

    check("E·matrix rows are proven shapes", matrix_rows_proven)
    check("E·SAPI probe honest on this host", sapi_probe_honest_here)
    check("E·auto-selector returns a real provider or the floor",
          auto_selector_lands_somewhere_real)


# ------------------------------------------------------------------- section F


def section_f(no_regression: bool = True) -> None:
    import nexus

    def identity() -> None:
        # floor style: later phases bump the version without breaking this
        parts = tuple(int(p) for p in nexus.__version__.split(".")[:3])
        assert parts >= (0, 19, 0), nexus.__version__
        assert nexus.NEXUS_PHASE >= 19

    def stdlib_only_core() -> None:
        """Speech's module-top imports stay stdlib — engines load lazily."""
        import sys

        stdlib = set(sys.stdlib_module_names)
        speech_dir = ROOT / "nexus" / "speech"
        offenders: list[str] = []
        for path in sorted(speech_dir.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:  # module top level only
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                for name in names:
                    if name not in stdlib and name != "nexus":  # first-party is free
                        offenders.append(f"{path.name}: {name}")
        assert not offenders, f"non-stdlib top-level imports: {offenders}"

    check("F·identity NEXUS_PHASE ≥ 19 · ≥ 0.19.0", identity)
    check("F·speech core stays stdlib-only at top level", stdlib_only_core)

    if not no_regression:
        return
    for phase in (15, 16, 17, 18):
        def _run(phase: int = phase) -> None:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", f"tests/phase{phase}", "-q",
                 "-p", "no:cacheprovider", "--ignore-glob=*test_device_proof*"],
                capture_output=True, text=True, timeout=900, cwd=str(ROOT),
            )
            assert proc.returncode == 0, f"phase {phase} regression:\n{proc.stdout[-800:]}"
        check(f"F·phase {phase} suite stays green", _run)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-regression", action="store_true")
    args = ap.parse_args()

    print("PHASE 19 — Speech System — Exit Gate")
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f(no_regression=not args.no_regression)

    print("-" * 60)
    print(f"PASSED {len(PASSED)}  FAILED {len(FAILED)}")
    for line in FAILED:
        print(f"  ✗ {line}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
