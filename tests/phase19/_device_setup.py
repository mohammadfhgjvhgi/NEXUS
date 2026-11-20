#!/usr/bin/env python3
"""Device-side one-shot: diagnose SAPI + spawn the MODE B setup batch.

Runs ON the box via code_run_tests.  The spawned batch installs
sherpa-onnx + numpy, downloads the whisper-tiny model and extracts it
— all in the background (the bridge gate is short); progress lands in
``M:\\NEXUS\\_speech_setup.log``.
"""

from __future__ import annotations

import subprocess


def test_sapi_diagnosis(capsys) -> None:
    from nexus.speech.providers.sapi import _PROBE_SCRIPT, _run_powershell, sapi_available

    row = sapi_available(refresh=True)
    print("SAPI_PROBE:", row.as_dict())
    try:
        out = _run_powershell(_PROBE_SCRIPT, timeout=60)
        print("SAPI_RAW:", out[:300].replace("\r\n", " | "))
    except Exception as exc:  # noqa: BLE001 — the diagnosis IS the point
        print("SAPI_EXC:", type(exc).__name__, str(exc)[:200])
    captured = capsys.readouterr()
    print(captured.out)


def test_spawn_mode_b_setup() -> None:
    """Fire the detached setup batch — returns immediately."""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        ["cmd", "/c", r"M:\NEXUS\_speech_setup.bat"],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
