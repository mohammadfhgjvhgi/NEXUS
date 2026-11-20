"""Secret Handling (New Plan §21.6 · Spec §160).

The credential architecture, verbatim (Spec §160)::

    Credential
    ├── ID | Provider | Scope | Reference | Created | last-used

and its law: **الـAgent يحصل على reference — ليس النص السري نفسه** —
the agent receives the *reference*, not the secret text itself.

The vault is the only place a secret text exists.  Every surface it
exposes — :meth:`SecretVault.list_credentials`, ``as_dict``, ``repr``,
the audit trail — carries references and metadata only.  Resolution
(:meth:`SecretVault.resolve`) is audited *without* the text and
advances the credential's ``last-used``.  The vault also answers the
§21.10 question directly: :meth:`SecretVault.scrub` removes every
stored secret's exact text from an arbitrary payload — catching the
secret that matches no known redaction pattern — and
:meth:`SecretVault.contains` is the door check.

Storage is in-memory and thread-safe (one lock; §2.1 keeps the core
stdlib-only, and so does the vault).

خزنة الأسرار — النص داخلها وحدها، والخارج مراجع فقط؛ وتنظّف النصّ
الدقيق من أي حمولة قبل أن يلمس الأبواب الأربعة.

Stdlib only.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Mapping
from typing import Any

from .contracts import Credential, SecretError, redact_preview
from .redaction import Redactor


class SecretVault:
    """The §21.6 vault — references out, text never out."""

    def __init__(self, redactor: Redactor | None = None) -> None:
        self._redactor = redactor
        self._lock = threading.Lock()
        self._secrets: dict[str, str] = {}
        self._credentials: dict[str, Credential] = {}
        self._audit: list[dict[str, str]] = []

    # ------------------------------------------------------------ storage

    def store(
        self,
        provider: str,
        secret: str,
        *,
        scope: str = "task",
        name: str = "",
    ) -> Credential:
        """Store *secret* under *provider* — returns the reference
        :class:`Credential` (never the text)."""
        if not provider or not provider.strip():
            raise SecretError("credential provider is empty")
        if not secret:
            raise SecretError(f"refusing to store an empty secret for {provider!r}")
        credential_id = f"sec_{uuid.uuid4().hex[:12]}"
        reference = f"vault://{provider.strip()}/{credential_id}"
        credential = Credential(
            id=credential_id,
            provider=provider.strip(),
            scope=scope or "task",
            reference=reference,
        )
        with self._lock:
            self._secrets[credential_id] = secret
            self._credentials[credential_id] = credential
            self._audit.append(
                {
                    "event": "store",
                    "credential": credential_id,
                    "provider": credential.provider,
                    "scope": credential.scope,
                    "name": name,
                }
            )
        return credential

    def store_from_environment(
        self,
        variables: Mapping[str, str],
        *,
        scope: str = "environment",
    ) -> tuple[Credential, ...]:
        """Store every *present* environment variable in *variables*
        (``{"github": "GITHUB_TOKEN"}``) — absent ones are skipped
        honestly, present ones return their references."""
        stored: list[Credential] = []
        for provider, env_name in variables.items():
            value = os.environ.get(env_name, "")
            if value:
                stored.append(self.store(provider, value, scope=scope, name=env_name))
        return tuple(stored)

    # ---------------------------------------------------------- resolution

    def resolve(self, reference: str) -> str:
        """Resolve *reference* to the secret text — audited without it.

        This is the single secure channel into the vault; callers use
        it at execution time only, and nothing they log may carry the
        result (the §21.10 guards watch the doors).
        """
        credential_id = self._id_from(reference)
        with self._lock:
            credential = self._credentials.get(credential_id)
            if credential is None or credential_id not in self._secrets:
                raise SecretError(f"unknown credential reference {reference!r}")
            self._credentials[credential_id] = Credential(
                id=credential.id,
                provider=credential.provider,
                scope=credential.scope,
                reference=credential.reference,
                created=credential.created,
                last_used=self._now(),
            )
            self._audit.append({"event": "resolve", "credential": credential_id})
            return self._secrets[credential_id]

    def forget(self, reference: str) -> None:
        """Drop a credential (id or reference) from the vault."""
        credential_id = self._id_from(reference)
        with self._lock:
            if credential_id not in self._secrets:
                raise SecretError(f"unknown credential reference {reference!r}")
            del self._secrets[credential_id]
            del self._credentials[credential_id]
            self._audit.append({"event": "forget", "credential": credential_id})

    # ---------------------------------------------------------- §21.10 half

    def scrub(self, text: str) -> tuple[str, int]:
        """Remove every stored secret's *exact* text from *text* —
        the exact-match half of the sink guard (catches secrets that
        match no redaction pattern)."""
        cleaned = text or ""
        hits = 0
        with self._lock:
            for secret in list(self._secrets.values()):
                if secret and secret in cleaned:
                    hits += cleaned.count(secret)
                    cleaned = cleaned.replace(secret, "[REDACTED:vault]")
        return cleaned, hits

    def contains(self, text: str) -> bool:
        """True when *text* still carries a stored secret verbatim."""
        if not text:
            return False
        with self._lock:
            return any(secret and secret in text for secret in self._secrets.values())

    # ------------------------------------------------------------- surface

    def get(self, reference: str) -> Credential:
        """The credential record (six §160 fields — no text)."""
        credential = self._credentials.get(self._id_from(reference))
        if credential is None:
            raise SecretError(f"unknown credential reference {reference!r}")
        return credential

    def list_credentials(self) -> tuple[Credential, ...]:
        """Every credential — references only, by design."""
        with self._lock:
            return tuple(self._credentials.values())

    def audit_trail(self) -> tuple[dict[str, str], ...]:
        """The vault's own audit trail — events and ids, never text."""
        with self._lock:
            return tuple(dict(entry) for entry in self._audit)

    def as_dict(self) -> dict[str, Any]:
        """A JSON-safe, text-free snapshot of the vault."""
        with self._lock:
            return {
                "credentials": [c.as_dict() for c in self._credentials.values()],
                "audit": [dict(entry) for entry in self._audit],
            }

    def __repr__(self) -> str:
        with self._lock:
            return f"SecretVault(credentials={len(self._credentials)})"

    def __len__(self) -> int:
        with self._lock:
            return len(self._credentials)

    # ------------------------------------------------------------ internals

    @staticmethod
    def _id_from(reference: str) -> str:
        """Accept a bare id or a full ``vault://provider/id`` reference."""
        text = (reference or "").strip()
        if text.startswith("vault://"):
            text = text.rsplit("/", 1)[-1]
        return text

    @staticmethod
    def _now() -> str:
        from ..verification.contracts import utc_now_iso

        return utc_now_iso()


def make_vault(redactor: Redactor | None = None) -> SecretVault:
    """The house vault (its own audit trail carries no text — the
    optional *redactor* is accepted for surface symmetry with the
    guards, the exact-match scrub needs none)."""
    return SecretVault(redactor=redactor)


__all__ = ["Credential", "SecretError", "SecretVault", "make_vault", "redact_preview"]
