"""Phase-21 rules tests — §21.10 the four guarded doors."""

from __future__ import annotations

import pytest

from nexus.security import (
    PROTECTED_SINKS,
    SecretLeakError,
    SecurityError,
    make_rules,
)

# built by concatenation — no secret-shaped literal in this file
PLANT_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
PLANT_PLAIN = "office-wifi-passphrase-2026"  # matches no pattern


def test_sinks_verbatim_and_guard_rejects_unknown() -> None:
    assert PROTECTED_SINKS == ("memory", "normal_chat", "logs", "activity")
    rules = make_rules()
    for sink in PROTECTED_SINKS:
        assert rules.guard(sink, "clean text") == "clean text"
    with pytest.raises(SecurityError):
        rules.guard("telemetry", "x")  # not one of the four §21.10 sinks


def test_pattern_secret_never_reaches_any_sink() -> None:
    """Every one of the four doors catches the same planted key."""
    rules = make_rules()
    dirty = f"the key is {PLANT_AWS} keep it safe"
    for sink in PROTECTED_SINKS:
        clean = rules.guard(sink, dirty)
        assert PLANT_AWS not in clean, sink
        assert "[REDACTED:aws_access_key]" in clean, sink


def test_patternless_secret_caught_by_vault_scrub() -> None:
    """§21.6+§21.10 — a secret matching no pattern is still caught
    verbatim, because the vault knows the text it holds."""
    rules = make_rules()
    rules.vault.store("legacy-app", PLANT_PLAIN, scope="task")
    dirty = f"connect with {PLANT_PLAIN} please"
    for sink in PROTECTED_SINKS:
        clean = rules.guard(sink, dirty)
        assert PLANT_PLAIN not in clean, sink
        assert "[REDACTED:vault]" in clean, sink


def test_named_doors_map_to_sinks() -> None:
    rules = make_rules()
    dirty = f"key {PLANT_AWS}"
    assert rules.guard_memory(dirty) == rules.guard("memory", dirty)
    assert rules.guard_chat(dirty) == rules.guard("normal_chat", dirty)
    assert rules.guard_logs(dirty) == rules.guard("logs", dirty)
    assert rules.guard_activity(dirty) == rules.guard("activity", dirty)


def test_assert_clean_raises_on_dirty_payload() -> None:
    rules = make_rules()
    rules.vault.store("legacy-app", PLANT_PLAIN)
    rules.assert_clean("totally clean payload")
    with pytest.raises(SecretLeakError):
        rules.assert_clean(f"carry {PLANT_PLAIN} inside")
    with pytest.raises(SecretLeakError):
        rules.assert_clean(f"carry {PLANT_AWS} inside")


def test_rules_surface_is_text_free() -> None:
    rules = make_rules()
    rules.vault.store("legacy-app", PLANT_PLAIN)
    rendered = str(rules.as_dict())
    assert PLANT_PLAIN not in rendered
    assert rules.as_dict()["protected_sinks"] == list(PROTECTED_SINKS)
    assert rules.as_dict()["vault_credentials"] == 1
