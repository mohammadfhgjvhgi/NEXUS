"""Phase-19 fixtures — real speech, real expectations, one honest double.

The six §19.3 fixtures are *real neural speech* committed as
text-safe base64 (the tunnel writes text-mode; base64 is immune to
the LF→CRLF law) with a manifest carrying the expected transcript,
expected intent and the whisper-tiny reference transcript as
provenance.  :class:`ScriptedProvider` is the deterministic test
double — always labelled ``scripted``, never passed off as an engine.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from nexus.speech.contracts import (
    AudioInput,
    LanguageDetection,
    ProviderUnavailableError,
    SpeechProvider,
    TranscriptionResult,
)
from nexus.speech.textnorm import script_inferred_language
from nexus.speech.wavio import load_wav

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_manifest() -> dict:
    """The fixture manifest — provenance included, verbatim."""
    return json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))


def fixture_wav_bytes(fixture_id: str) -> bytes:
    """One fixture's real WAV bytes — decoded from its armored file."""
    for row in load_manifest()["fixtures"]:
        if row["id"] == fixture_id:
            raw = (FIXTURES_DIR / row["file"]).read_text(encoding="ascii")
            return base64.b64decode(raw)
    raise KeyError(f"unknown fixture {fixture_id!r}")


def fixture_audio(fixture_id: str) -> AudioInput:
    """One fixture as a real :class:`AudioInput` (voice:// provenance)."""
    return load_wav(fixture_wav_bytes(fixture_id), source_uri=f"voice://fixture/{fixture_id}")


def manifest_rows() -> list[dict]:
    return load_manifest()["fixtures"]


class ScriptedProvider(SpeechProvider):
    """A deterministic double — labelled ``scripted``, never an engine.

    ``responses`` maps a ``source_uri`` to the transcript it returns;
    anything unlisted yields ``default``.  Language comes from honest
    script inference over the text it returned.
    """

    name = "scripted"

    def __init__(self, responses: dict[str, str] | None = None, default: str = "") -> None:
        self._responses = dict(responses or {})
        self._default = default
        self.calls: list[str] = []

    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        self.calls.append(audio.source_uri)
        text = self._responses.get(audio.source_uri, self._default)
        return TranscriptionResult(
            text=text,
            language=script_inferred_language(text) if text else "",
            confidence=0.99,
            provider=self.name,
            latency_seconds=0.001,
        )

    def detect_language(self, audio: AudioInput) -> LanguageDetection:
        result = self.transcribe(audio)
        if not result.text:
            raise ProviderUnavailableError(
                f"scripted provider has no transcript for {audio.source_uri}"
            )
        return LanguageDetection(
            language=result.language,
            confidence=result.confidence,
            method="script-inference",
            provider=self.name,
        )

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "mode": "scripted test double (deterministic)",
            "installed": "True",
            "detail": "not a recognition engine — fixtures only",
        }
