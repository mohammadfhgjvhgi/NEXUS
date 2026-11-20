"""Security Rules (New Plan §21.10).

The rule, verbatim::

    لا يصل secret إلى:
    Memory · Normal chat · Logs · Activity

Enforced *structurally*, not by caller discipline.  Every protected
sink's door is :meth:`SecurityRules.guard`, and the door does two
passes:

1. **exact** — the vault removes every stored secret's verbatim text
   (:meth:`SecretVault.scrub`) — this catches a secret that matches
   no known pattern, because the vault knows the text it holds;
2. **pattern** — the §21.7 redactor removes credential-shaped spans
   (API keys, bearer headers, URLs with credentials, assignments…).

If anything survives both passes, :class:`SecretLeakError` is raised —
the hard stop — instead of a silently dirty payload.  The four sinks
have named doors (``guard_memory`` · ``guard_chat`` · ``guard_logs``
· ``guard_activity``) so callers wire the right sink by construction,
and the audit/activity factories accept the guards directly
(:mod:`nexus.security.audit`).

قواعد الأمن — الأبواب الأربعة محروسة بمرورين (الدقيق ثم الأنماط)،
وما نجا من الاثنين يوقف كل شيء.

Stdlib only.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    PROTECTED_SINKS,
    SecretLeakError,
    SecurityError,
)
from .redaction import Redactor, make_redactor
from .secrets import SecretVault, make_vault


class SecurityRules:
    """§21.10 — the four guarded doors."""

    def __init__(
        self,
        *,
        vault: SecretVault | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self.vault = vault or make_vault()
        self.redactor = redactor or make_redactor()

    # ----------------------------------------------------------------- API

    def guard(self, sink: str, text: str) -> str:
        """Clean *text* for *sink* — the §21.10 door.

        Exact vault pass → pattern pass → the hard stop.  Returns the
        clean text; raises :class:`SecretLeakError` only if a secret
        survives both passes (which the two passes themselves make
        effectively unreachable — the belt and the braces).
        """
        if sink not in PROTECTED_SINKS:
            raise SecurityError(
                f"sink {sink!r} is not one of the protected sinks {PROTECTED_SINKS}"
            )
        cleaned, _ = self.vault.scrub(text or "")
        cleaned, _ = self.redactor.redact(cleaned)
        if self.vault.contains(cleaned):
            raise SecretLeakError(
                f"a stored secret survived both passes toward sink {sink!r}"
            )
        return cleaned

    def guard_memory(self, text: str) -> str:
        """The Memory door — nothing enters §12 carrying a secret."""
        return self.guard("memory", text)

    def guard_chat(self, text: str) -> str:
        """The Normal chat door — the user never reads a secret."""
        return self.guard("normal_chat", text)

    def guard_logs(self, text: str) -> str:
        """The Logs door — machine logs carry findings, not secrets."""
        return self.guard("logs", text)

    def guard_activity(self, text: str) -> str:
        """The Activity door — the friendly feed stays friendly."""
        return self.guard("activity", text)

    # ------------------------------------------------------------- checks

    def assert_clean(self, text: str) -> None:
        """Raise :class:`SecretLeakError` if *text* still looks secret
        (pattern) or is a stored secret verbatim (exact)."""
        if self.vault.contains(text or ""):
            raise SecretLeakError("payload carries a stored secret verbatim")
        if self.redactor.contains_secret(text or ""):
            raise SecretLeakError("payload carries a secret-shaped span")

    def as_dict(self) -> dict[str, Any]:
        """The guard's own surface — sink names and counts, no text."""
        return {
            "protected_sinks": list(PROTECTED_SINKS),
            "vault_credentials": len(self.vault),
        }


def make_rules(
    *,
    vault: SecretVault | None = None,
    redactor: Redactor | None = None,
) -> SecurityRules:
    """The house rules (its own vault by default)."""
    return SecurityRules(vault=vault, redactor=redactor)


__all__ = [
    "PROTECTED_SINKS",
    "Redactor",
    "SecretLeakError",
    "SecurityError",
    "SecurityRules",
    "make_rules",
]
