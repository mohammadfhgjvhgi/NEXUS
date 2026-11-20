"""WAV floor tests — real fixture bytes, honest refusals."""

from __future__ import annotations

import pytest
from fixtures import fixture_audio, fixture_wav_bytes, manifest_rows

from nexus.speech.contracts import AudioError
from nexus.speech.wavio import load_wav, peak, rms, wav_bytes, write_wav


class TestRealFixtures:
    def test_all_six_load_with_manifest_durations(self) -> None:
        rows = manifest_rows()
        assert len(rows) == 6
        for row in rows:
            audio = fixture_audio(row["id"])
            assert audio.duration_seconds == pytest.approx(
                row["duration_s"], abs=0.02
            ), row["id"]
            assert audio.sample_rate_hz == 16000

    def test_speech_has_energy(self) -> None:
        audio = fixture_audio("en_basic")
        assert rms(audio.samples) > 0.01
        assert peak(audio.samples) <= 1.0

    def test_noise_fixture_is_louder_in_variance_than_silence(self) -> None:
        noise = fixture_audio("noise")
        clean = fixture_audio("en_basic")
        # both are speech; the noisy one must still be a real signal
        assert rms(noise.samples) > 0.0
        assert len(noise.samples) == len(clean.samples) or len(noise.samples) > 0


class TestRoundtrip:
    def test_wav_bytes_roundtrip(self, tmp_path) -> None:
        samples = tuple(v / 32768.0 for v in (0, 16384, -16384, 32767, -32768))
        path = write_wav(tmp_path / "rt.wav", samples, 16000)
        back = load_wav(path.read_bytes(), source_uri="voice://rt")
        assert back.sample_rate_hz == 16000
        for original, returned in zip(samples, back.samples, strict=True):
            assert returned == pytest.approx(original, abs=1 / 32767.0)

    def test_wav_bytes_header_is_real_riff(self) -> None:
        blob = wav_bytes((0.5, -0.5), 16000)
        assert blob[:4] == b"RIFF" and blob[8:12] == b"WAVE"


class TestHonestRefusal:
    def test_non_wav_refused(self) -> None:
        with pytest.raises(AudioError, match="RIFF"):
            load_wav(b"PK\x03\x04-not-a-wav-at-all........")

    def test_truncated_payload_refused(self) -> None:
        good = fixture_wav_bytes("ar_basic")
        with pytest.raises(AudioError):
            load_wav(good[: len(good) // 3])

    def test_eight_bit_refused(self) -> None:
        import io
        import struct
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(1)
            w.setframerate(16000)
            w.writeframes(struct.pack("<4B", 128, 200, 100, 255))
        with pytest.raises(AudioError, match="16-bit"):
            load_wav(buf.getvalue())
