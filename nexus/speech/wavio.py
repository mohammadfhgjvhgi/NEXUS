"""WAV I/O floor (New Plan §19.1) — stdlib parsing, honest refusal.

The speech system's guaranteed floor: real RIFF/WAVE parsing with the
stdlib ``wave`` module, 16-bit PCM mono (stereo downmixed by mean),
samples normalized to ``[-1.0, 1.0]``.  Anything else is an
:class:`AudioError` — never a silent guess.  Writing back (``wav_bytes``,
``write_wav``) exists for the SAPI file path (MODE A feeds a real file)
and for the fixtures' roundtrip tests.

أرضية قراءة/كتابة WAV بالمكتبة القياسية فقط — ما لا يُفهم يُرفض بصدق.
"""

from __future__ import annotations

import io
import struct
import wave
from pathlib import Path

from .contracts import AudioError, AudioInput

_RIFF_MAGIC = b"RIFF"
_WAVE_MAGIC = b"WAVE"


def load_wav(data: bytes, *, source_uri: str = "") -> AudioInput:
    """Parse real WAV bytes → :class:`AudioInput`.

    16-bit PCM only (the format every engine in this phase consumes);
    stereo is downmixed to mono by per-frame mean.  Corrupt, foreign or
    empty payloads raise :class:`AudioError` with the reason.
    """
    if len(data) < 12 or data[:4] != _RIFF_MAGIC or data[8:12] != _WAVE_MAGIC:
        raise AudioError("not a RIFF/WAVE container — refusing to guess")
    buf = io.BytesIO(data)
    try:
        with wave.open(buf) as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            declared_frames = w.getnframes()
            frames = w.readframes(declared_frames)
    except wave.Error as exc:
        raise AudioError(f"unreadable WAV payload: {exc}") from exc
    if rate <= 0:
        raise AudioError(f"invalid sample rate {rate}")
    if width != 2:
        raise AudioError(
            f"only 16-bit PCM is supported, got {width * 8}-bit — refusing to guess"
        )
    # integrity: the data chunk must actually hold what the header declares
    expected_bytes = declared_frames * channels * width
    if len(frames) < expected_bytes:
        raise AudioError(
            f"truncated WAV — header declares {declared_frames} frames, "
            f"payload holds {len(frames) // (channels * width)}"
        )
    count = len(frames) // (2 * channels)
    if count == 0:
        raise AudioError("WAV contains no frames")
    ints = struct.unpack(f"<{count * channels}h", frames[: count * channels * 2])
    if channels == 1:
        samples = [v / 32768.0 for v in ints]
    else:
        samples = [
            sum(ints[i : i + channels]) / (channels * 32768.0)
            for i in range(0, len(ints), channels)
        ]
    return AudioInput(
        sample_rate_hz=rate,
        samples=tuple(samples),
        source_uri=source_uri or "memory://audio",
    )


def wav_bytes(samples: tuple[float, ...] | list[float], sample_rate_hz: int) -> bytes:
    """Mono 16-bit PCM WAV bytes from float samples (SAPI's file path)."""
    if sample_rate_hz <= 0:
        raise AudioError(f"sample rate must be positive, got {sample_rate_hz}")
    if not samples:
        raise AudioError("cannot serialize empty samples")
    clipped = (max(-1.0, min(1.0, s)) for s in samples)
    ints = [int(round(s * 32767.0)) for s in clipped]
    payload = struct.pack(f"<{len(ints)}h", *ints)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate_hz)
        w.writeframes(payload)
    return buf.getvalue()


def write_wav(path: str | Path, samples: tuple[float, ...] | list[float],
              sample_rate_hz: int) -> Path:
    """Serialize to a real file — the handle opens and closes here."""
    p = Path(path)
    p.write_bytes(wav_bytes(samples, sample_rate_hz))
    return p


def rms(samples: tuple[float, ...] | list[float]) -> float:
    """Root-mean-square — the level proxy behind noise diagnostics."""
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def peak(samples: tuple[float, ...] | list[float]) -> float:
    """Absolute peak amplitude."""
    if not samples:
        return 0.0
    return max(abs(s) for s in samples)
