"""Redaction (New Plan §21.7 · Spec §161).

Spec §161, verbatim — secrets must not appear in::

    Chat | Logs | Memory | Telemetry | Errors | Screenshots

The redactor is the *pattern* half of the §21.10 defense (the vault's
exact-match scrub is the other half — a secret that matches no known
pattern is still known verbatim by its vault).  Every finding carries
its kind; every cleaned payload replaces the secret span with
``[REDACTED:<kind>]`` — the marker names *what* was hidden, never
*what it was*.

The §21.9 secret scanner runs through the same redactor: even a
finding's snippet is redacted before it becomes a report line.

محرك التنقية — كل أنماط الأسرار تُستبدل بعلامة [REDACTED:<kind>]،
والملفّ نفسه لا يحمل النص السري أبداً.

Stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import SecurityError

#: The replacement marker — names the *kind*, never the value.
REDACTED_MARK = "[REDACTED:{kind}]"


@dataclass(frozen=True, slots=True)
class RedactionFinding:
    """One secret-shaped span — its kind and its char position."""

    kind: str
    start: int
    length: int

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "start": self.start, "length": self.length}


def _assignment_repl(match: re.Match[str]) -> str:
    """Keep ``key=`` / ``"key":`` and replace only the value."""
    return f"{match.group(1)}{match.group(2)}{REDACTED_MARK.format(kind='assignment')}"


def _basic_url_repl(match: re.Match[str]) -> str:
    """``scheme://user:pass@host`` → ``scheme://[REDACTED:credentials]@host``."""
    scheme, _creds, rest = match.group(1), match.group(2), match.group(3)
    return f"{scheme}://{REDACTED_MARK.format(kind='credentials')}@{rest}"


def _compile_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """The named pattern set (order matters — first match wins per span)."""
    assignment = (
        r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?token|"
        r"auth[_-]?token|client[_-]?secret|private[_-]?key|session[_-]?token|"
        r"refresh[_-]?token|token)\b(\s*[=:]\s*[\"']?)"
        r"(?!\[REDACTED:)[^\s\"',;]{4,}"
    )
    return (
        ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("github_token", re.compile(r"\b(?:ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,})\b")),
        ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
        ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
        ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
        ("bearer_header", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}")),
        ("private_key_header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
        ("credentials_in_url", re.compile(
            r"\b([a-z][a-z0-9+.-]*)://([^\s/:@]+:[^\s/@]+)@([^\s]*)" , re.IGNORECASE,
        )),
        ("secret_assignment", re.compile(assignment)),
    )


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = _compile_patterns()

#: Keys whose *whole value* is sensitive (JSON/YAML bodies) — the value
#: is redacted even when it matches no pattern shape.
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?token|"
    r"auth[_-]?token|client[_-]?secret|private[_-]?key|session[_-]?token|"
    r"refresh[_-]?token|token)"
)


class Redactor:
    """Pattern-based redaction (§21.7) — the shared cleaning surface."""

    def __init__(self, extra_patterns: Iterable[tuple[str, str]] = ()) -> None:
        self._patterns: list[tuple[str, re.Pattern[str]]] = list(_PATTERNS)
        for kind, pattern in extra_patterns:
            self._patterns.append((kind, re.compile(pattern)))

    # ---------------------------------------------------------------- API

    def findings(self, text: str) -> tuple[RedactionFinding, ...]:
        """Every secret-shaped span in *text* (kinds in pattern order)."""
        found: list[RedactionFinding] = []
        for kind, pattern in self._patterns:
            for match in pattern.finditer(text or ""):
                found.append(
                    RedactionFinding(
                        kind=kind, start=match.start(), length=match.end() - match.start()
                    )
                )
        return tuple(found)

    def contains_secret(self, text: str) -> bool:
        """True when *text* carries at least one secret-shaped span."""
        return any(
            pattern.search(text or "") is not None for _, pattern in self._patterns
        )

    def redact(self, text: str) -> tuple[str, int]:
        """Clean *text* — returns ``(clean_text, findings_count)``.

        Assignment-shaped matches keep their key and lose their value;
        every other match is replaced whole.
        """
        cleaned = text or ""
        total = 0
        for kind, pattern in self._patterns:
            if not pattern.search(cleaned):
                continue
            if kind == "secret_assignment":
                cleaned, n = pattern.subn(_assignment_repl, cleaned)
            elif kind == "credentials_in_url":
                cleaned, n = pattern.subn(_basic_url_repl, cleaned)
            else:
                cleaned, n = pattern.subn(REDACTED_MARK.format(kind=kind), cleaned)
            total += n
        return cleaned, total

    def redact_to_safe(self, text: str) -> str:
        """Clean *text*, returning only the cleaned string."""
        return self.redact(text)[0]

    def redact_mapping(self, mapping: Mapping[str, Any]) -> dict[str, Any]:
        """Clean every value of a mapping (recursively) — and a value
        under a sensitive-named key is redacted whole, pattern or not."""
        cleaned: dict[str, Any] = {}
        for key, value in mapping.items():
            if isinstance(value, str):
                if _SENSITIVE_KEY_RE.search(str(key)):
                    cleaned[key] = REDACTED_MARK.format(kind="assignment")
                else:
                    cleaned[key] = self.redact_to_safe(value)
            elif isinstance(value, Mapping):
                cleaned[key] = self.redact_mapping(value)
            elif isinstance(value, (list, tuple)):
                cleaned[key] = [
                    self.redact_to_safe(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                cleaned[key] = value
        return cleaned


def make_redactor(extra_patterns: Iterable[tuple[str, str]] = ()) -> Redactor:
    """The house redactor (shared by vault, audit, rules, trivy)."""
    return Redactor(extra_patterns)


__all__ = [
    "REDACTED_MARK",
    "RedactionFinding",
    "Redactor",
    "SecurityError",
    "make_redactor",
]
