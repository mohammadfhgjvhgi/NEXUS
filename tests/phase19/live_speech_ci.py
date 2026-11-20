#!/usr/bin/env python3
"""Phase-19 live proof — the §19 system against real audio, this host.

Nine rungs, each printing ``[PASS]``/``[FAIL]`` (the device wrapper
parses them):

1.  fixtures-real      — the six armored fixtures decode to real RIFF/WAVE
                         audio at the manifest's durations;
2.  wavio-laws         — corrupt / truncated / foreign payloads refused;
3.  normalization-real — Arabic · English · mixed through one law;
4.  wer-math           — known-answer WER + the manifest's whisper
                         reference transcripts scoring as recorded;
5.  intent-real        — the router classifies the six real utterances
                         (≥5/6 — the noise case may honestly miss);
6.  providers-honest   — the capability matrix probes truthfully and the
                         refusal floor refuses;
7.  pipeline-machinery — five verbatim stages over the scripted double;
8.  memory-bridge      — a voice task remembered into a real §12 engine
                         and recalled with its provenance;
9.  provider-live      — STRICT: a real engine must transcribe a real
                         fixture (wer sanity), unless the operator opted
                         out with NEXUS_SPEECH_ALLOW_NULL=1 (CI hosts).

Exit 0 only when every rung holds.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (  # noqa: E402
    FIXTURES_DIR,
    ScriptedProvider,
    fixture_wav_bytes,
    manifest_rows,
)

from nexus.memory.engine import MemoryEngine  # noqa: E402
from nexus.memory.store import SQLiteMemoryStore  # noqa: E402
from nexus.speech.contracts import (  # noqa: E402
    PIPELINE_STAGES,
    AudioError,
    ProviderUnavailableError,
)
from nexus.speech.intent import IntentRouter  # noqa: E402
from nexus.speech.memory import SpeechMemory  # noqa: E402
from nexus.speech.pipeline import VoicePipeline  # noqa: E402
from nexus.speech.providers import available_providers, create_provider  # noqa: E402
from nexus.speech.providers.null import NullProvider  # noqa: E402
from nexus.speech.providers.sapi import sapi_available  # noqa: E402
from nexus.speech.providers.sherpa import sherpa_available  # noqa: E402
from nexus.speech.textnorm import normalize_text  # noqa: E402
from nexus.speech.wavio import load_wav  # noqa: E402
from nexus.speech.wer import word_error_rate  # noqa: E402

PASSED = 0


def rung(name: str, fn) -> None:
    global PASSED
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001 — a rung fails loudly
        print(f"[FAIL] {name} — {type(exc).__name__}: {exc}")
        return
    PASSED += 1
    print(f"[PASS] {name} — {detail}")


# ------------------------------------------------------------------ rungs


def rung_fixtures_real() -> str:
    rows = manifest_rows()
    assert len(rows) == 6, f"expected 6 fixtures, got {len(rows)}"
    durations = []
    for row in rows:
        raw = (FIXTURES_DIR / row["file"]).read_text(encoding="ascii")
        wav = base64.b64decode(raw)
        assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE", row["id"]
        audio = load_wav(wav, source_uri=f"voice://fixture/{row['id']}")
        assert abs(audio.duration_seconds - row["duration_s"]) < 0.02, row["id"]
        durations.append(round(audio.duration_seconds, 2))
    return f"6 real utterances: {durations}s @16kHz"


def rung_wavio_laws() -> str:
    good = fixture_wav_bytes("en_basic")
    for bad, why in (
        (b"PK\x03\x04 not a wav container .....", "foreign bytes"),
        (good[: len(good) // 3], "truncation"),
    ):
        try:
            load_wav(bad)
        except AudioError:
            continue
        raise AssertionError(f"{why} was accepted")
    return "foreign + truncated refused honestly"


def rung_normalization_real() -> str:
    rows = {r["id"]: r for r in manifest_rows()}
    assert normalize_text("Open the Browser.") == "open the browser"
    assert normalize_text(rows["ar_basic"]["expected_text"]).startswith("افتح")
    mixed = normalize_text(rows["mixed"]["expected_text"])
    assert "terminal" in mixed and "npm" in mixed
    return "ar · en · mixed — one law per token"


def rung_wer_math() -> str:
    assert word_error_rate("open the browser", "Open the Browser.") == 0.0
    assert word_error_rate("a b c", "a x c") > 0.0
    rows = {r["id"]: r for r in manifest_rows()}
    for fid in ("en_basic", "fast"):
        wer = word_error_rate(rows[fid]["expected_text"],
                              rows[fid]["whisper_tiny_reference_transcript"])
        assert wer == 0.0, f"{fid} reference drifted: {wer}"
    ar = word_error_rate(rows["ar_basic"]["expected_text"],
                         rows["ar_basic"]["whisper_tiny_reference_transcript"])
    assert 0.0 < ar <= 1.5
    return f"known answers hold; whisper-tiny Arabic reference WER={ar:.2f}"


def rung_intent_real() -> str:
    router = IntentRouter()
    rows = manifest_rows()
    hits = sum(
        1 for r in rows if router.route(r["expected_text"]).intent == r["expected_intent"]
    )
    assert hits >= 5, f"only {hits}/6 utterances routed to their intent"
    return f"{hits}/6 real utterances routed correctly (noise may miss)"


def rung_providers_honest() -> str:
    rows = {r["provider"]: r for r in available_providers()}
    assert rows["null"]["installed"] == "False"
    try:
        NullProvider().transcribe(None)  # type: ignore[arg-type]
    except ProviderUnavailableError:
        pass
    else:
        raise AssertionError("the refusal floor did not refuse")
    sherpa = sherpa_available()
    sapi = sapi_available()
    assert isinstance(sherpa.installed, bool) and isinstance(sapi.installed, bool)
    if not sherpa.installed:
        assert "pip install" in sherpa.detail
    return (
        f"sherpa installed={sherpa.installed} model={sherpa.model_found} · "
        f"sapi installed={sapi.installed} ({sapi.recognizer_count} recognizers)"
    )


def rung_pipeline_machinery() -> str:
    responses = {
        f"voice://fixture/{row['id']}": row["whisper_tiny_reference_transcript"]
        for row in manifest_rows()
    }
    provider = ScriptedProvider(responses)
    audio = load_wav(fixture_wav_bytes("en_basic"), source_uri="voice://fixture/en_basic")
    result = VoicePipeline(provider).run(audio)
    assert [t.name for t in result.traces] == list(PIPELINE_STAGES)
    assert result.ok and result.task is not None
    assert result.task.task_kind == "open_application"
    return f"stages verbatim · task={result.task.task_kind} intent={result.task.intent}"


def rung_memory_bridge() -> str:
    responses = {"voice://fixture/en_basic": "Open the browser and run the tests"}
    with tempfile.TemporaryDirectory() as raw:
        memory = MemoryEngine(SQLiteMemoryStore(str(Path(raw) / "mem.sqlite")))
        try:
            sink = SpeechMemory(memory)
            result = VoicePipeline(
                ScriptedProvider(responses), memory_sink=sink
            ).run(load_wav(fixture_wav_bytes("en_basic"),
                           source_uri="voice://fixture/en_basic"))
            assert result.ok
            hits = sink.recall("voice task", limit=5)
            assert hits, "voice task not recallable"
            fact = [h for h in hits if h["type"] == "fact"][0]
            assert fact["sources"][0]["method"] == "user_statement"
        finally:
            memory.close()  # real-Windows law: close before temp cleanup
    return "voice task remembered + recalled with provenance (engine closed)"


def rung_provider_live() -> str:
    provider = create_provider()
    audio = load_wav(fixture_wav_bytes("en_basic"),
                     source_uri="voice://fixture/en_basic")
    rows = {r["id"]: r for r in manifest_rows()}
    if provider.name == "null":
        if os.environ.get("NEXUS_SPEECH_ALLOW_NULL") == "1":
            return "no engine on this host (operator opt-out) — machinery proven above"
        raise AssertionError(
            "no speech engine available and NEXUS_SPEECH_ALLOW_NULL is unset"
        )
    result = provider.transcribe(audio)
    expected = rows["en_basic"]["expected_text"]
    assert result.text.strip(), f"{provider.name} produced no transcript"
    wer = word_error_rate(expected, result.text)
    assert wer < 0.7, f"{provider.name} wer={wer:.2f} beyond sanity ({result.text!r})"
    detail = f"provider={provider.name} hypothesis={result.text!r} wer={wer:.2f}"
    if provider.name == "sherpa-onnx":
        detection = provider.detect_language(load_wav(
            fixture_wav_bytes("ar_basic"), source_uri="voice://fixture/ar_basic"
        ))
        assert detection.language, "whisper emitted no language token"
        detail += f" · ar detect={detection.language} ({detection.method})"
    return detail


def main() -> int:
    print("PHASE 19 — Speech System — live proof")
    rung("1 fixtures-real", rung_fixtures_real)
    rung("2 wavio-laws", rung_wavio_laws)
    rung("3 normalization-real", rung_normalization_real)
    rung("4 wer-math", rung_wer_math)
    rung("5 intent-real", rung_intent_real)
    rung("6 providers-honest", rung_providers_honest)
    rung("7 pipeline-machinery", rung_pipeline_machinery)
    rung("8 memory-bridge", rung_memory_bridge)
    rung("9 provider-live", rung_provider_live)
    print(f"{PASSED}/9 rungs passed")
    return 0 if PASSED == 9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
