"""sherpa-onnx provider (New Plan §19.2) — k2-fsa/sherpa-onnx behind
the NEXUS SpeechProvider contract.

Integration mode, per the plan: **MODE A/B** — the engine is used
*directly* when it is installed and a model is present (MODE A), and
its *absence is reported honestly* (:class:`ProviderUnavailableError`)
so the SAPI floor or the null provider keep the pipeline honest
(MODE B semantics — the §19.4 pipeline never sees a vendor type).

The engine: ``sherpa_onnx.OfflineRecognizer.from_whisper`` over the
Whisper ONNX family — multilingual (Arabic included), file-based,
runs fully offline on the CPU.  ``detect_language`` is *native* here:
whisper emits a language token per stream, exposed as ``result.lang``.

The pin follows the house pinning law (docling ``>=2.25,<3``,
qdrant-client ``>=1.19,<2``): one documented, bounded range —
installable via the ``[speech]`` extra.

sherpa-onnx (§19.2) — MODE A مباشرة عند التثبيت ووجود النموذج،
وغيابه يُقال بصدق ولا يُفترض أبداً.

Stdlib at module top (sherpa-onnx + numpy import lazily, guarded).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import (
    CONFIDENCE_UNREPORTED,
    AudioInput,
    LanguageDetection,
    ProviderUnavailableError,
    SpeechProvider,
    TranscriptionError,
    TranscriptionResult,
)

#: The documented §19.2 pin — bounded, installable, never floating.
SHERPA_ONNX_PIN = "sherpa-onnx>=1.10,<2"

#: Model discovery override (a directory with encoder/decoder/tokens).
MODEL_DIR_ENV = "NEXUS_SPEECH_MODEL_DIR"

_PROBE: SherpaAvailability | None = None


@dataclass(frozen=True, slots=True)
class SherpaModelConfig:
    """The three files whisper needs — explicit, never guessed."""

    encoder: str
    decoder: str
    tokens: str
    language: str = ""  # "" → whisper auto-detect (native detect_language)
    task: str = "transcribe"
    num_threads: int = 2


@dataclass(frozen=True, slots=True)
class SherpaAvailability:
    """The honest probe result — installed? which version? model found?"""

    installed: bool
    version: str = ""
    model_found: bool = False
    model_dir: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "installed": str(self.installed),
            "version": self.version,
            "model_found": str(self.model_found),
            "model_dir": self.model_dir,
            "detail": self.detail,
        }


def _model_dir_candidates(directory: str | Path | None) -> list[Path]:
    """Discovery order: explicit → env → the repo-root default.

    The default keeps the device flow zero-config: a model extracted
    under ``<repo root>/models/sherpa-onnx-whisper-tiny`` (the release
    archive's own layout) is found without any environment variable.
    """
    candidates: list[Path] = []
    if directory:
        candidates.append(Path(directory))
    env = os.environ.get(MODEL_DIR_ENV, "")
    if env:
        candidates.append(Path(env))
    candidates.append(
        Path(__file__).resolve().parents[3] / "models" / "sherpa-onnx-whisper-tiny"
    )
    return candidates


def _config_in(base: Path) -> SherpaModelConfig | None:
    encoders = sorted(base.glob("*encoder*.onnx"))
    decoders = sorted(base.glob("*decoder*.onnx"))
    tokens = sorted(base.glob("*tokens*.txt"))
    if not encoders or not decoders or not tokens:
        return None

    def _prefer_int8(paths: list[Path]) -> Path:
        for p in paths:
            if ".int8." in p.name:
                return p
        return paths[0]

    return SherpaModelConfig(
        encoder=str(_prefer_int8(encoders)),
        decoder=str(_prefer_int8(decoders)),
        tokens=str(tokens[0]),
    )


def discover_model_config(directory: str | Path | None = None) -> SherpaModelConfig | None:
    """Find whisper files in a model directory — int8 preferred.

    Layout is the official release layout (``sherpa-onnx-whisper-tiny``):
    ``*encoder*.onnx``, ``*decoder*.onnx``, ``*tokens*.txt``.  Returns
    ``None`` when nothing usable is found — never a half-config.
    """
    for base in _model_dir_candidates(directory):
        if base.is_dir():
            config = _config_in(base)
            if config is not None:
                return config
    return None


def sherpa_available(
    *, model_dir: str | Path | None = None, refresh: bool = False
) -> SherpaAvailability:
    """Probe the host for sherpa-onnx *and* a usable model — truth only.

    The result is cached (the probe imports a heavy package); pass
    ``refresh=True`` to re-probe after an install.
    """
    global _PROBE  # noqa: PLW0603 — one cached probe, refreshed on demand
    if _PROBE is not None and not refresh:
        return _PROBE
    try:
        import importlib.util

        spec = importlib.util.find_spec("sherpa_onnx")
        if spec is None:
            _PROBE = SherpaAvailability(
                installed=False,
                detail=f"not installed — install with: pip install {SHERPA_ONNX_PIN!r}",
            )
            return _PROBE
        import sherpa_onnx  # type: ignore[import-not-found]

        version = str(getattr(sherpa_onnx, "__version__", "") or "unknown")
        config = discover_model_config(model_dir)
        if config is None:
            _PROBE = SherpaAvailability(
                installed=True,
                version=version,
                model_found=False,
                model_dir=str(model_dir or os.environ.get(MODEL_DIR_ENV, "")),
                detail=(
                    "engine installed but no whisper model found — set "
                    f"{MODEL_DIR_ENV} to a directory with *encoder*.onnx, "
                    "*decoder*.onnx and *tokens*.txt"
                ),
            )
            return _PROBE
        _PROBE = SherpaAvailability(
            installed=True,
            version=version,
            model_found=True,
            model_dir=str(Path(config.encoder).parent),
        )
        return _PROBE
    except Exception as exc:  # noqa: BLE001 — any import failure is honest absence
        _PROBE = SherpaAvailability(
            installed=False, detail=f"present but unusable: {type(exc).__name__}: {exc}"
        )
        return _PROBE


class SherpaOnnxProvider(SpeechProvider):
    """§19.2 — the sherpa-onnx whisper engine behind the NEXUS contract."""

    name = "sherpa-onnx"

    def __init__(
        self,
        model: SherpaModelConfig | None = None,
        *,
        recognizer_factory: Any = None,
    ) -> None:
        """``recognizer_factory`` is the test seam — an injected callable
        returning an object with ``create_stream``/``decode_stream``
        (the MODE A *direct use* proof without a 140 MB model)."""
        self._model = model if model is not None else discover_model_config(None)
        self._factory = recognizer_factory
        self._recognizer: Any = None

    # ------------------------------------------------------------ §19.1

    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        recognizer = self._ensure_recognizer()
        started = time.monotonic()
        try:
            # the injected seam (tests) receives the raw samples — numpy
            # is the REAL engine's dependency, not the contract's
            samples = audio.samples if self._factory is not None else _as_float32(audio)
            stream = recognizer.create_stream()
            stream.accept_waveform(audio.sample_rate_hz, samples)
            recognizer.decode_stream(stream)
            result = stream.result
        except ProviderUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 — the engine failed, say how
            raise TranscriptionError(
                f"sherpa-onnx transcription failed: {type(exc).__name__}: {exc}"
            ) from exc
        text = str(getattr(result, "text", "") or "").strip()
        return TranscriptionResult(
            text=text,
            language=str(getattr(result, "lang", "") or "").strip(),
            confidence=CONFIDENCE_UNREPORTED,  # whisper reports no score — honest
            provider=self.name,
            latency_seconds=time.monotonic() - started,
        )

    def detect_language(self, audio: AudioInput) -> LanguageDetection:
        if self._model is not None and self._model.language:
            # pinned at load — reported as configured, never as a guess
            return LanguageDetection(
                language=self._model.language,
                method="configured",
                provider=self.name,
            )
        result = self.transcribe(audio)
        if not result.language:
            raise TranscriptionError("sherpa-onnx emitted no language token")
        return LanguageDetection(
            language=result.language, method="native", provider=self.name
        )

    # ---------------------------------------------------------- plumbing

    def _ensure_recognizer(self) -> Any:
        if self._recognizer is not None:
            return self._recognizer
        if self._factory is not None:
            # injected engine (the MODE A direct-use proof)
            self._recognizer = self._factory()
            return self._recognizer
        availability = sherpa_available(refresh=self._model is None)
        if not availability.installed:
            raise ProviderUnavailableError(
                f"sherpa-onnx is not available on this host ({availability.detail})"
            )
        if not availability.model_found:
            raise ProviderUnavailableError(
                f"sherpa-onnx is installed but no whisper model is configured "
                f"({availability.detail})"
            )
        assert self._model is not None  # model_found ⇒ config resolved
        try:
            import sherpa_onnx  # type: ignore[import-not-found]

            self._recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=self._model.encoder,
                decoder=self._model.decoder,
                tokens=self._model.tokens,
                language=self._model.language,
                task=self._model.task,
                num_threads=self._model.num_threads,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailableError(
                f"sherpa-onnx could not load the model: {type(exc).__name__}: {exc}"
            ) from exc
        return self._recognizer

    def describe(self) -> dict[str, Any]:
        if self._factory is not None:
            return {
                "provider": self.name,
                "pin": SHERPA_ONNX_PIN,
                "mode": "injected-engine (test seam)",
                "languages": "multilingual (whisper)",
            }
        availability = sherpa_available()
        return {
            "provider": self.name,
            "pin": SHERPA_ONNX_PIN,
            "mode": "A (direct use) when installed + model present",
            "detect_language": "native (whisper language token)",
            **availability.as_dict(),
        }


def _as_float32(audio: AudioInput) -> Any:
    """tuple[float] → numpy float32 (numpy ships with sherpa-onnx)."""
    try:
        import numpy  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 — honest dependency report
        raise ProviderUnavailableError(
            f"numpy is required by the sherpa-onnx provider ({exc})"
        ) from exc
    return numpy.asarray(audio.samples, dtype=numpy.float32)
