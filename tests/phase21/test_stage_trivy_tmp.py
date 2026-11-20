"""Trivy staged on M:\\NEXUS\\tools-bin (2026-09-10) — see PHASE-21-REPORT.md."""


def test_trivy_staging_record() -> None:
    from pathlib import Path

    assert Path(r"M:\\NEXUS\\tools-bin\\trivy.exe").is_file()
    assert Path(r"M:\\NEXUS\\tools-bin\\trivy-cache\\db\\metadata.json").is_file()
