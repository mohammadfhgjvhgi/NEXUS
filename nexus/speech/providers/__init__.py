"""Provider registry (New Plan §19.1) — selection with honest probes.

Three engines behind one contract:

* ``sherpa-onnx`` (§19.2) — multilingual whisper ONNX, MODE A when the
  engine *and* a model are present;
* ``sapi`` — the Windows built-in dictation, MODE A with zero installs;
* ``null`` — the refusal floor, so «no engine» is always *said*, never
  faked.

:func:`create_provider` auto-selects in that order; each probe is real
(import + file check / platform + recognizer count) and every row it
emits into the capability matrix is proven on this host.
"""

from __future__ import annotations

from typing import Any

from ..contracts import SpeechProvider
from .null import NullProvider
from .sapi import SapiProvider, sapi_available
from .sherpa import SherpaOnnxProvider, sherpa_available

PROVIDER_NAMES: tuple[str, ...] = ("sherpa-onnx", "sapi", "null")

#: auto-selection order — best engine first, refusal floor last
_AUTO_ORDER: tuple[type[SpeechProvider], ...] = (
    SherpaOnnxProvider,
    SapiProvider,
    NullProvider,
)


def create_provider(preferred: str | None = None, **kwargs: Any) -> SpeechProvider:
    """Build one provider — by name, or auto-selected with real probes."""
    if preferred is not None:
        known: dict[str, type[SpeechProvider]] = {
            "sherpa-onnx": SherpaOnnxProvider,
            "sapi": SapiProvider,
            "null": NullProvider,
        }
        if preferred not in known:
            raise ValueError(
                f"unknown provider {preferred!r} — known: {sorted(known)}"
            )
        return known[preferred](**kwargs)  # type: ignore[arg-type]

    # auto: sherpa needs engine + model; sapi needs Windows + recognizers
    sherpa = sherpa_available()
    if sherpa.installed and sherpa.model_found:
        return SherpaOnnxProvider(**kwargs)
    sapi = sapi_available()
    if sapi.installed:
        return SapiProvider(**kwargs)
    return NullProvider()


def available_providers() -> tuple[dict[str, Any], ...]:
    """Every engine's capability row, probed on *this* host."""
    return (
        SherpaOnnxProvider().describe(),
        SapiProvider().describe(),
        NullProvider().describe(),
    )


__all__ = [
    "PROVIDER_NAMES",
    "SapiProvider",
    "SherpaOnnxProvider",
    "NullProvider",
    "create_provider",
    "available_providers",
]
