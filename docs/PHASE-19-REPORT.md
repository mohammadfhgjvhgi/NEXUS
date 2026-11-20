# PHASE 19 — Speech System — Delivery Report

**Status:** ✅ COMPLETE — Implemented · Integrated · Tested · Verified · Documented · Committed
**Version:** `0.19.0` · `NEXUS_PHASE = 19` · New Plan §19 (19.1–19.4)

## What was built

Local voice control: real speech recognition engines behind one NEXUS
contract, a six-condition benchmark over real audio, and the verbatim
voice pipeline that lands real tasks in §12 memory.

### §19.1 — Speech API (`nexus/speech/contracts.py` + `wavio.py`)
- `SpeechProvider` (ABC): `transcribe(AudioInput) → TranscriptionResult`,
  `detect_language(AudioInput) → LanguageDetection`, `describe() →
  capability rows`.
- The detection **method is always stated**: `native` (whisper's
  language token) / `script-inference` (unicode ranges — SAPI's honest
  path) / `configured` (pinned at load).
- `CONFIDENCE_UNREPORTED = -1.0` — a provider without a score says so;
  `0.0` is reserved for a real «confidently wrong» engine number.
- `wavio`: stdlib `wave` parsing (16-bit PCM, stereo→mono downmix),
  `wav_bytes`/`write_wav` for the SAPI file path, `rms`/`peak`, and a
  real integrity law: a header declaring more frames than the payload
  holds is **truncated** → `AudioError`.
- `PIPELINE_STAGES` and `BENCHMARK_CONDITIONS` verbatim from the plan.

### §19.2 — sherpa-onnx (`providers/sherpa.py`, `providers/sapi.py`, `providers/null.py`)
- **Repository intake (real pull):** `k2-fsa/sherpa-onnx` cloned at
  `intake/sherpa-onnx` (59 MB, depth 1) and the Python binding analyzed
  from source: `OfflineRecognizer.from_whisper(encoder, decoder,
  tokens, language, task, num_threads)`, `create_stream()` →
  `accept_waveform(rate, float32)` → `decode_stream()` →
  `stream.result.text/.lang`.
- `sherpa_available()` probe: installed? version? model found?
  (`NEXUS_SPEECH_MODEL_DIR` → `discover_model_config` prefers int8).
  Pin: `sherpa-onnx>=1.10,<2` (`[speech]` extra; cp314 win_amd64 wheels
  verified on PyPI — the device's Python 3.14 is covered).
- **MODE A floor — Windows SAPI**: `System.Speech` dictation driven
  through one PowerShell script (`SetInputToWaveFile` →
  `DictationGrammar` → `Recognize(TimeSpan)`), zero installs, real
  confidence (0..100), base64 UTF-8 transport for transcripts, temp WAV
  handle closed before recognition (the WinError-32 law). Off-Windows
  the probe refuses honestly with the reason.
- **NullProvider**: the refusal floor — every verb raises
  `ProviderUnavailableError` with the install hint.
- `create_provider()` auto-selects: sherpa (engine+model) → sapi → null.

### §19.3 — Benchmark (`benchmark.py` + `tests/phase19/fixtures/`)
- Six real conditions verbatim: **Arabic · Arabic technical · English ·
  Mixed Arabic-English · Fast speech · Noise**.
- Fixtures are **real neural speech** (edge-tts `ar-SA-HamedNeural`,
  `en-US-GuyNeural rate=+45%`; z-ai TTS English) at 16 kHz mono PCM,
  committed as text-safe base64 + a manifest carrying generator,
  expected text, expected intent and the whisper-tiny reference
  transcript as provenance. The noise case is the clean English clip
  mixed with white Gaussian noise at ~5 dB SNR.
- `SpeechBenchmark.run()` → per-case `WER` (through the §19.4
  normalizer), detected language, intent verdict, latency → a JSON
  report that states numbers and judges nothing.

### §19.4 — Pipeline (`pipeline.py`, `intent.py`, `textnorm.py`, `memory.py`)
- `Microphone → STT → Normalization → Intent → Task` verbatim; a
  `StageTrace` per stage; the first failure stops the run with honest
  pending/failed traces. `FileAudioSource` is the proven floor;
  `MicAudioSource` refuses clearly until the device audio layer lands.
- `TextNormalizer`: tashkeel+tatweel strip, alef family unification,
  ة→ه / ى→ي / ؤ→و / ئ→ي, Arabic-Indic digits → Western, Latin
  lowercasing, per-token punctuation strip — one law for ar/en/mixed.
- `IntentRouter`: six NEXUS intents with bilingual triggers over
  normalized forms; deterministic winner law (first keyword wins);
  honest `unknown` below the confidence floor; the argument is the
  utterance remainder after the trigger.
- `SpeechMemory` over the §12 engine: `FACT` per voice task +
  `SUMMARY` per session, evidence
  `MemoryEvidence(method="user_statement", uri="voice://…")` (the §12
  evidence vocabulary's honest slot for a spoken utterance — its
  validator taught us the method list), `recall` keeps provenance.

## Verification

| Gate | Result |
| --- | --- |
| Tests (`tests/phase19`) | **104/104** |
| Exit criteria harness | **26/26**, zero regression (15·16·17·18) |
| Live proof (`live_speech_ci.py`) | **9/9** — fixtures · wavio · normalization · WER · intent · probes · pipeline · §12 memory · provider-live |
| MODE B real-engine rung (sandbox) | sherpa-onnx 1.13.7 + whisper-tiny: `wer=0.00` English, native `ar` detection |
| ruff / pyright | clean / 0 errors |
| CI | Phase 19 harness + `speech-live` job (Phases 1–19) |
| Device (M:\NEXUS) | deploy → per-file tests → 9-rung live proof → `proofs\phase19_live.json` → `PHASE19_COMPLETE.txt` |

## Device-relevant notes

- Fixtures travel as base64 **text** — the tunnel's text-mode writes
  (LF→CRLF) cannot corrupt them; the decoder discards whitespace.
- Rung 9 is strict on the device: SAPI (MODE A) or sherpa+model
  (MODE B) must really transcribe the English fixture; CI opts out
  explicitly with `NEXUS_SPEECH_ALLOW_NULL=1`.
- MODE B on the device: `pip install sherpa-onnx` (cp314 wheel exists)
  + whisper-tiny model under `M:\NEXUS\models\whisper-tiny` and
  `NEXUS_SPEECH_MODEL_DIR` pointing at it.
