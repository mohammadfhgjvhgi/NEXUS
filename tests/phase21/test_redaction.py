"""Phase-21 redaction tests — §21.7 patterns, markers, mapping cleaning.

Planted secrets are built by concatenation: no secret-shaped literal
sits in this file (the toolchain itself redacts such literals on
write — the §21.10 law enforced on NEXUS's own test suite).
"""

from __future__ import annotations

import pytest

from nexus.security import (
    REDACTED_MARK,
    Redactor,
    make_redactor,
)

_PLANT_PIECES = {
    "aws_access_key": ("AKIA", "IOSFODNN7EXAMPLE"),
    "github_token": ("ghp_", "0123456789abcdefghijklmnopqrstuvwxyzABCD"),
    "slack_token": ("xoxb-", "123456789012-ABCDEFghijklmnop"),
    "openai_style_key": ("sk-", "proj-abcdefghijklmnopqrstuvwx"),
    "google_api_key": ("AIza", "a" * 35),
    "private_key_header": ("-----BEGIN ", "RSA PRIVATE KEY-----"),
}
PLANTED: dict[str, str] = {
    name: "".join(pieces) for name, pieces in _PLANT_PIECES.items()
}
PLANTED["jwt"] = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c"
)


@pytest.fixture()
def redactor() -> Redactor:
    return make_redactor()


def test_aws_key_redacted(redactor: Redactor) -> None:
    clean, count = redactor.redact(f"key is {PLANTED['aws_access_key']} ok")
    assert count == 1
    assert PLANTED["aws_access_key"] not in clean
    assert "[REDACTED:aws_access_key]" in clean


def test_github_token_redacted(redactor: Redactor) -> None:
    clean, count = redactor.redact(f"use {PLANTED['github_token']} ok")
    assert count == 1 and "[REDACTED:github_token]" in clean
    assert "ghp_0123456789" not in clean


def test_slack_and_openai_keys_redacted(redactor: Redactor) -> None:
    text = f"{PLANTED['slack_token']} and {PLANTED['openai_style_key']}"
    clean, count = redactor.redact(text)
    assert count == 2
    assert "xoxb" not in clean and "sk-proj" not in clean


def test_google_key_and_jwt_redacted(redactor: Redactor) -> None:
    text = f"{PLANTED['google_api_key']} · {PLANTED['jwt']}"
    clean, count = redactor.redact(text)
    assert count == 2
    assert "AIza" not in clean and "eyJhbGciOiJIUz" not in clean


def test_bearer_header_redacted(redactor: Redactor) -> None:
    clean, count = redactor.redact("Authorization: Bearer abcdef0123456789abcdef")
    assert count == 1 and "abcdef0123456789" not in clean


def test_url_credentials_redacted(redactor: Redactor) -> None:
    clean, _ = redactor.redact("remote https://user:hunter2pass@github.com/ps/repo.git")
    assert "hunter2pass" not in clean
    assert "[REDACTED:credentials]@github.com" in clean
    assert clean.startswith("remote https://")


def test_assignment_keeps_key_loses_value(redactor: Redactor) -> None:
    clean, count = redactor.redact('password="hunter2secret" api_key = abcd1234efgh')
    assert count == 2
    assert "hunter2secret" not in clean and "abcd1234efgh" not in clean
    assert "password=" in clean and "api_key = " in clean
    assert clean.count(REDACTED_MARK.format(kind="assignment")) == 2


def test_private_key_header_redacted(redactor: Redactor) -> None:
    clean, count = redactor.redact(PLANTED["private_key_header"])
    assert count == 1 and "PRIVATE KEY" not in clean


def test_benign_text_untouched(redactor: Redactor) -> None:
    text = (
        "M:\\NEXUS\\nexus\\security\\rules.py — 21.10 says secrets never "
        "reach the four sinks; delete file = high risk; pytest 57/57 green."
    )
    clean, count = redactor.redact(text)
    assert count == 0 and clean == text
    assert not redactor.contains_secret(text)


def test_findings_name_the_kind(redactor: Redactor) -> None:
    findings = redactor.findings(f"use {PLANTED['aws_access_key']} now")
    assert len(findings) == 1
    assert findings[0].kind == "aws_access_key"
    assert findings[0].length == len(PLANTED["aws_access_key"])


def test_mapping_cleaning_recursive(redactor: Redactor) -> None:
    payload = {
        "note": "clean text",
        "creds": {"password": "hunter2secret", "host": "db.local"},
        "lines": [f"token: {PLANTED['github_token']}", "safe"],
        "count": 3,
    }
    cleaned = redactor.redact_mapping(payload)
    assert cleaned["note"] == "clean text"
    assert "hunter2secret" not in str(cleaned["creds"]) and cleaned["creds"]["host"] == "db.local"
    assert "ghp_0123456789" not in str(cleaned["lines"]) and cleaned["lines"][1] == "safe"
    assert "[REDACTED:github_token]" in str(cleaned["lines"])
    assert cleaned["count"] == 3


def test_extra_patterns_extend(redactor: Redactor) -> None:
    custom = Redactor(extra_patterns=[("nexus_pat", r"\bNXPAT-[A-Z0-9]{8,}\b")])
    clean, count = custom.redact("add NXPAT-ABCD1234 now")
    assert count == 1 and "NXPAT-ABCD1234" not in clean
    assert "[REDACTED:nexus_pat]" in clean
