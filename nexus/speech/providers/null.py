"""Null provider (New Plan §19.1) — the honest «no engine here».

When neither sherpa-onnx (§19.2 MODE A) nor the Windows SAPI floor is
usable, this is what the auto-selector returns: every verb raises
:class:`ProviderUnavailableError` with the *install hint*, and the
capability matrix says exactly what is missing.  What it never does is
pretend — no fake transcripts, no invented confidence.
"""

from __future__ import annotations

from typing import Any

from ..contracts import (
    AudioInput,
    LanguageDetection,
    ProviderUnavailableError,
    SpeechProvider,
    TranscriptionResult,
)
from .sherpa import SHERPA_ONNX_PIN

_HINT = f"{SHERPA_ONNX_PIN} (the [speech] extra)"


class NullProvider(SpeechProvider):
    """The refusal every missing engine deserves — loudly and honestly."""

    name = "null"

    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        raise ProviderUnavailableError(
            "no speech provider is available on this host — install "
            f"sherpa-onnx {_HINT} or run on Windows with SAPI (MODE A)"
        )

    def detect_language(self, audio: AudioInput) -> LanguageDetection:
        raise ProviderUnavailableError(
            "no speech provider is available on this host — install "
            f"sherpa-onnx {_HINT} or run on Windows with SAPI (MODE A)"
        )

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "installed": "False",
            "mode": "refusal floor — no engine on this host",
            "detail": f"install sherpa-onnx {_HINT} or use the Windows SAPI "
            "floor (MODE A)",
        }
