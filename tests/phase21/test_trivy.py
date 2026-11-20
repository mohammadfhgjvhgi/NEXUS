"""Phase-21 trivy tests — §21.9 kinds, MODE A parsing, MODE B honesty."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.security import (
    SCAN_KINDS,
    BaselineScanner,
    ScanReport,
    SecurityError,
    TrivyScanner,
    TrivyUnavailable,
    make_scanner,
)

# built by concatenation — no secret-shaped literal in this file
PLANT_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
PLANT_GHP = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyzABCD"

# a trivy fs --format json payload shape (vuln + secret + license + packages)
TRIVY_PAYLOAD = {
    "SchemaVersion": 2,
    "ArtifactName": "fixture",
    "Results": [
        {
            "Target": "requirements.txt",
            "Class": "lang-pkgs",
            "Type": "pip",
            "Packages": [
                {"Name": "requests", "Version": "2.19.0"},
                {"Name": "urllib3", "Version": "1.24.1"},
            ],
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2023-32681",
                    "PkgName": "requests",
                    "InstalledVersion": "2.19.0",
                    "Severity": "HIGH",
                    "Title": "Proxy-Authorization header leak on redirect",
                }
            ],
            "Secrets": [
                {
                    "RuleID": "aws-access-key-id",
                    "Category": "aws",
                    "Severity": "CRITICAL",
                    "Title": "AWS access key",
                    "Match": PLANT_AWS,
                    "StartLine": 3,
                }
            ],
            "Licenses": [
                {"Name": "MIT", "Category": "notice", "Severity": "LOW", "FilePath": "LICENSE"}
            ],
        }
    ],
}


@pytest.fixture()
def repo_tree(tmp_path: Path) -> Path:
    root = tmp_path / "fixture-repo"
    root.mkdir()
    (root / "requirements.txt").write_text(
        "requests==2.19.0\nurllib3==1.24.1\n# a comment\n-r extra.txt\n",
        encoding="utf-8",
    )
    (root / "extra.txt").write_text("click>=8.0\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nlicense = "MIT"\ndependencies = ["rich>=13"]\n',
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026\n", encoding="utf-8")
    (root / "app.py").write_text(
        "# SPDX-License-Identifier: MIT\n"
        "TOKEN = '" + PLANT_GHP + "'\n"
        "KEY = '" + PLANT_AWS + "'\n",
        encoding="utf-8",
    )
    return root


def test_scan_kinds_enforced(tmp_path: Path) -> None:
    scanner = BaselineScanner()
    with pytest.raises(SecurityError):
        scanner.scan(tmp_path, "radius")
    with pytest.raises(SecurityError):
        scanner.scan(tmp_path / "missing", "secret")


def test_baseline_dependency_inventory(repo_tree: Path) -> None:
    report = BaselineScanner().scan(repo_tree, "dependency")
    assert report.mode == "baseline" and report.kind == "dependency"
    rules = {f.rule_id for f in report.findings}
    assert {"requests", "urllib3", "rich"} <= rules  # real manifests parsed
    assert report.count == 3  # -r includes are documented out of scope


def test_baseline_secret_scan_finds_and_redacts(repo_tree: Path) -> None:
    report = BaselineScanner().scan(repo_tree, "secret")
    kinds = {f.rule_id for f in report.findings}
    assert {"github_token", "aws_access_key"} <= kinds
    # §21.10: the finding's snippet is redacted — the secret is not re-printed
    rendered = str(report.as_dict())
    assert PLANT_AWS not in rendered and PLANT_GHP not in rendered
    assert "[REDACTED:" in rendered


def test_baseline_license_detection(repo_tree: Path) -> None:
    report = BaselineScanner().scan(repo_tree, "license")
    rules = {f.rule_id for f in report.findings}
    assert "MIT" in rules  # pyproject declared + SPDX header
    assert "license-file" in rules  # the LICENSE file itself


def test_baseline_vulnerability_scan_is_honest(repo_tree: Path) -> None:
    """Zero findings + a note — a baseline never invents a vulnerability."""
    report = BaselineScanner().scan(repo_tree, "vulnerability")
    assert report.count == 0
    assert report.findings == ()
    assert any("trivy" in note for note in report.notes)
    assert "cannot judge" in report.notes[0]


def test_baseline_scan_all_four_kinds(repo_tree: Path) -> None:
    reports = BaselineScanner().scan_all(repo_tree)
    assert tuple(reports) == SCAN_KINDS
    assert all(isinstance(r, ScanReport) for r in reports.values())
    assert reports["dependency"].count > 0


def test_trivy_mode_a_parsing(repo_tree: Path) -> None:
    """The MODE A parser on a real payload shape (no binary needed)."""
    real = TrivyScanner(binary="/nonexistent/trivy")
    real._version = "Version: 0.0.0-test"  # version cache — no probe
    findings = real._parse(TRIVY_PAYLOAD, "vulnerability")
    assert len(findings) == 1
    assert findings[0].rule_id == "CVE-2023-32681"
    assert findings[0].severity == "HIGH"
    assert findings[0].location.startswith("requests@")
    secrets = real._parse(TRIVY_PAYLOAD, "secret")
    assert secrets[0].rule_id == "aws-access-key-id"
    assert PLANT_AWS not in secrets[0].description  # redacted at parse time
    deps = real._parse(TRIVY_PAYLOAD, "dependency")
    assert {d.rule_id for d in deps} == {"requests", "urllib3"}
    licenses = real._parse(TRIVY_PAYLOAD, "license")
    assert licenses[0].rule_id == "MIT"


def test_trivy_unavailable_raises_honestly(tmp_path: Path) -> None:
    scanner = TrivyScanner(binary="/nonexistent/trivy")
    assert scanner.available() is False
    with pytest.raises(TrivyUnavailable):
        scanner.scan(tmp_path, "secret")


def test_make_scanner_mode_matches_host() -> None:
    """MODE A when trivy exists here, MODE B honestly when it does not."""
    scanner = make_scanner()
    if TrivyScanner().available():
        assert isinstance(scanner, TrivyScanner)
    else:
        assert isinstance(scanner, BaselineScanner)


def test_scan_report_severity_counts_and_json(repo_tree: Path) -> None:
    report = BaselineScanner().scan(repo_tree, "secret")
    counts = report.severity_counts()
    assert counts.get("HIGH", 0) == report.count
    as_dict = report.as_dict()
    assert as_dict["mode"] == "baseline"
    assert json.dumps(as_dict)  # JSON-safe
