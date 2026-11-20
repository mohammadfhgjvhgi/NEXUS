"""Windows SAPI provider (New Plan §19.1) — the zero-install MODE A floor.

Windows ships a real speech recognizer (SAPI 5.1, ``System.Speech``)
on every desktop since Vista — dictation over a WAV file, offline, no
pip install.  This provider drives it through one PowerShell script:

    SetInputToWaveFile → LoadGrammar(DictationGrammar) → Recognize

so the §19.1 ``transcribe`` verb works *out of the box* on the user's
Windows box — exactly the «Windows-first» law.  SAPI reports a real
confidence (0..100) per recognition; it has no language detector, so
``detect_language`` uses script inference over the transcript and says
so (``method="script-inference"``) — the matrix never dresses
inference up as a native engine report.

Everything refuses honestly off-Windows: the probe is the truth, not
a hope.  Arabic dictation depends on the host's installed SAPI
recognizers (usually en-US) — the capability matrix reports the
cultures actually found.

أرضية الوضع A — SAPI المدمج في Windows بلا أي تثبيت، والرفض صادق خارجها.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import (
    AudioInput,
    LanguageDetection,
    ProviderUnavailableError,
    SpeechProvider,
    TranscriptionResult,
)
from ..textnorm import script_inferred_language
from ..wavio import wav_bytes

_PROBE: SapiAvailability | None = None


@dataclass(frozen=True, slots=True)
class SapiAvailability:
    """The honest probe result — usable? which recognizers exist?"""

    installed: bool
    recognizer_count: int = 0
    cultures: tuple[str, ...] = ()
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "installed": str(self.installed),
            "recognizer_count": str(self.recognizer_count),
            "cultures": ",".join(self.cultures),
            "detail": self.detail,
        }


_PROBE_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$rs = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
Write-Output ("COUNT=" + $rs.Count)
foreach ($r in $rs) { Write-Output ("CULTURE=" + $r.Culture.Name) }
"""

_TRANSCRIBE_TEMPLATE = r"""
Add-Type -AssemblyName System.Speech
$reco = New-Object System.Speech.Recognition.SpeechRecognitionEngine
try {{
    $reco.SetInputToWaveFile('{path}')
    $grammar = New-Object System.Speech.Recognition.DictationGrammar
    $reco.LoadGrammar($grammar)
    $result = $reco.Recognize([TimeSpan]::FromSeconds({seconds}))
    if ($null -ne $result) {{
        $bytes = [Text.Encoding]::UTF8.GetBytes($result.Text)
        Write-Output ("B64=" + [Convert]::ToBase64String($bytes))
        Write-Output ("CONF=" + $result.Confidence)
    }} else {{
        Write-Output "B64="
        Write-Output "CONF=0"
    }}
}} finally {{
    $reco.Dispose()
}}
"""


def sapi_available(*, refresh: bool = False) -> SapiAvailability:
    """Probe the host for a usable SAPI recognizer — truth only."""
    global _PROBE  # noqa: PLW0603 — one cached probe, refreshed on demand
    if _PROBE is not None and not refresh:
        return _PROBE
    if sys.platform != "win32":
        _PROBE = SapiAvailability(
            installed=False,
            detail=(
                f"SAPI exists only on Windows (this is {sys.platform}) — "
                "the MODE A floor refuses honestly off-Windows"
            ),
        )
        return _PROBE
    try:
        out = _run_powershell(_PROBE_SCRIPT)
        count, cultures = 0, []
        for line in out.splitlines():
            if line.startswith("COUNT="):
                count = int(line.split("=", 1)[1] or "0")
            elif line.startswith("CULTURE="):
                cultures.append(line.split("=", 1)[1])
        _PROBE = SapiAvailability(
            installed=count > 0,
            recognizer_count=count,
            cultures=tuple(cultures),
            detail="" if count else "no SAPI recognizer installed on this host",
        )
        return _PROBE
    except Exception as exc:  # noqa: BLE001 — probe failure is honest absence
        _PROBE = SapiAvailability(
            installed=False, detail=f"probe failed: {type(exc).__name__}: {exc}"
        )
        return _PROBE


class SapiProvider(SpeechProvider):
    """§19.1 — the Windows built-in recognizer behind the NEXUS contract."""

    name = "sapi"

    def __init__(self, *, timeout_seconds: float = 120.0) -> None:
        self._timeout = timeout_seconds

    # ------------------------------------------------------------ §19.1

    def transcribe(self, audio: AudioInput) -> TranscriptionResult:
        availability = sapi_available()
        if not availability.installed:
            raise ProviderUnavailableError(
                f"SAPI is not available on this host ({availability.detail})"
            )
        started = time.monotonic()
        payload = wav_bytes(audio.samples, audio.sample_rate_hz)
        # Real-Windows law (phases 17/18): mkstemp opens an OS handle —
        # close it before the recognizer reads the file, and remove it
        # in a finally.
        fd, name = tempfile.mkstemp(suffix=".wav", prefix="nexus-sapi-")
        os.close(fd)
        tmp = Path(name)
        script = _TRANSCRIBE_TEMPLATE.format(
            path=str(tmp).replace("'", "''"),
            seconds=max(5.0, audio.duration_seconds + 5.0),
        )
        try:
            tmp.write_bytes(payload)
            out = _run_powershell(script, timeout=self._timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderUnavailableError(
                f"SAPI recognition timed out after {self._timeout:.0f}s"
            ) from exc
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass  # best effort — never mask the real outcome
        text, confidence = "", -1.0
        for line in out.splitlines():
            if line.startswith("B64="):
                raw = line[4:]
                if raw:
                    text = base64.b64decode(raw).decode("utf-8", errors="replace")
            elif line.startswith("CONF="):
                try:
                    confidence = float(line[5:]) / 100.0
                except ValueError:
                    confidence = -1.0
        return TranscriptionResult(
            text=text.strip(),
            language=script_inferred_language(text) if text else "",
            confidence=confidence,
            provider=self.name,
            latency_seconds=time.monotonic() - started,
        )

    def detect_language(self, audio: AudioInput) -> LanguageDetection:
        result = self.transcribe(audio)
        if not result.text:
            raise ProviderUnavailableError(
                "SAPI produced no transcript to infer a language from — "
                "check the recognizer's installed culture"
            )
        return LanguageDetection(
            language=script_inferred_language(result.text),
            confidence=result.confidence,
            method="script-inference",
            provider=self.name,
        )

    def describe(self) -> dict[str, Any]:
        availability = sapi_available()
        return {
            "provider": self.name,
            "mode": "A (Windows built-in — zero installs)",
            "engine": "SAPI 5.1 System.Speech dictation (file input)",
            "detect_language": "script-inference (SAPI has no native detector)",
            **availability.as_dict(),
        }


# ----------------------------------------------------------- plumbing


def _run_powershell(script: str, *, timeout: float = 120.0) -> str:
    """One PowerShell invocation — UTF-8 tolerant, honest failures."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProviderUnavailableError(
            "powershell.exe not found on PATH — not a Windows host?"
        ) from exc
    if proc.returncode != 0:
        raise ProviderUnavailableError(
            f"SAPI PowerShell failed (rc={proc.returncode}): {proc.stderr.strip()[:300]}"
        )
    return proc.stdout
