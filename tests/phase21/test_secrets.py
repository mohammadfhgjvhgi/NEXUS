"""Phase-21 secret-handling tests — §21.6 the reference law, the vault."""

from __future__ import annotations

import pytest

from nexus.security import (
    Credential,
    SecretError,
    make_vault,
)

SECRET = "nexus-super-secret-text-7f3a9"
SECRET_NO_PATTERN = "plain-horse-battery- staple"  # no known pattern shape


def test_store_returns_reference_not_text() -> None:
    """§160 — the agent receives the reference, not the secret itself."""
    vault = make_vault()
    credential = vault.store("github", SECRET, scope="task")
    assert isinstance(credential, Credential)
    assert credential.provider == "github"
    assert credential.reference.startswith("vault://github/")
    # the six-field surface and repr never carry the text
    rendered = str(credential.as_dict()) + repr(credential) + repr(vault)
    assert SECRET not in rendered
    assert credential.as_dict()["last_used"] == ""


def test_resolve_is_audited_and_advances_last_used() -> None:
    vault = make_vault()
    credential = vault.store("github", SECRET)
    first = credential.as_dict()["created"]
    assert vault.resolve(credential.reference) == SECRET
    refreshed = vault.get(credential.reference)
    assert refreshed.last_used != ""
    assert refreshed.last_used >= first  # ISO-8601 lexicographic works here
    # the vault's audit trail records the event, never the text
    trail = str(vault.audit_trail())
    assert SECRET not in trail
    assert '"event": "resolve"' in trail or "'event': 'resolve'" in trail


def test_unknown_reference_raises() -> None:
    vault = make_vault()
    with pytest.raises(SecretError):
        vault.resolve("vault://github/sec_missing")
    with pytest.raises(SecretError):
        vault.get("sec_missing")
    with pytest.raises(SecretError):
        vault.forget("sec_missing")


def test_empty_secret_and_provider_refused() -> None:
    vault = make_vault()
    with pytest.raises(SecretError):
        vault.store("github", "")
    with pytest.raises(SecretError):
        vault.store("  ", SECRET)


def test_scrub_removes_exact_secret_even_without_pattern() -> None:
    """The §21.10 exact-match half — a patternless secret is still caught."""
    vault = make_vault()
    vault.store("legacy", SECRET_NO_PATTERN)
    payload = f"the credential is {SECRET_NO_PATTERN} inside"
    clean, hits = vault.scrub(payload)
    assert hits == 1
    assert SECRET_NO_PATTERN not in clean
    assert "[REDACTED:vault]" in clean
    assert vault.contains(payload) and not vault.contains(clean)


def test_list_and_snapshot_are_text_free() -> None:
    vault = make_vault()
    vault.store("github", SECRET, name="GITHUB_TOKEN")
    vault.store("openai", "sk-proj-abcdefghijklmnopqrstuvwx")
    snapshot = str(vault.as_dict())
    assert SECRET not in snapshot and "sk-proj" not in snapshot
    assert len(vault.list_credentials()) == 2
    assert all(isinstance(c, Credential) for c in vault.list_credentials())
    assert len(vault) == 2


def test_forget_drops_the_secret() -> None:
    vault = make_vault()
    credential = vault.store("tmp", SECRET)
    vault.forget(credential.id)
    assert len(vault) == 0
    with pytest.raises(SecretError):
        vault.resolve(credential.reference)


def test_store_from_environment_skips_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = make_vault()
    monkeypatch.setenv("NEXUS_TEST_TOKEN", SECRET)
    monkeypatch.delenv("NEXUS_TEST_ABSENT", raising=False)
    stored = vault.store_from_environment(
        {"github": "NEXUS_TEST_TOKEN", "absent": "NEXUS_TEST_ABSENT"}
    )
    assert len(stored) == 1
    assert stored[0].provider == "github"
    assert stored[0].scope == "environment"


def test_credential_id_or_reference_both_resolve() -> None:
    vault = make_vault()
    credential = vault.store("github", SECRET)
    assert vault.resolve(credential.id) == SECRET
    assert vault.resolve(credential.reference) == SECRET
