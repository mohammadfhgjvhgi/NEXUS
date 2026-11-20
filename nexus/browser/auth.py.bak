"""Browser Authentication (Final Build Plan §11.5 / Spec §209).

Spec §209, verbatim intent:

    NEXUS يدعم مواقع تتطلب تسجيل دخول — لكن:
    - لا يعرض كلمات المرور في logs.
    - لا ينسخ secrets إلى memory.
    - لا يرسلها لخدمة خارجية بلا سبب.
    - لا يحاول تجاوز الحماية.

The structural answer: **secrets never cross the tool interface.**

* Storage — :class:`BrowserVault` keeps entries encrypted at rest
  with Windows **DPAPI** (``CryptProtectData`` via pure ctypes — the
  Phase-8 ctypes discipline, no keyloggable key material anywhere).
  The vault file lives under ``<data>/browser/vault.bin``; off win32
  storing is refused honestly (no degraded plaintext mode, ever).
* Injection — the ``browser`` tool accepts a **vault reference**
  (``vault_ref: "site"``) instead of the secret text: the handler
  resolves it inside the engine seam and types it straight into the
  page. The plaintext therefore never appears in tool arguments,
  outputs, the ``tool.called/completed`` events, logs, or the memory
  system — there is nothing to redact because nothing leaks.
* Storage path — a secret enters the vault from a **file path**
  (scope-checked by the §8.2 stage) or an environment variable; the
  store call rides events carrying only the path/env name, never the
  value.
* Defense in depth — :meth:`redact` scrubs any echo of a known
  secret from browser tool outputs (pages sometimes echo input).

الخزنة — DPAPI بـctypes خالصة، والأسرار لا تعبر واجهة الأداة:
مرجعٌ يُحلّ داخل محرك الصفحة، وتخزينٌ عبر مسار ملف، وتنقيحٌ
كخط دفاع أخير.

Stdlib only.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wintypes
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("nexus.browser")

#: The redaction mask — the only string that may stand for a secret.
REDACTED = "[REDACTED]"


class VaultError(Exception):
    """A vault operation refused or failed — honest, never leaky."""


# ------------------------------------------------------------- DPAPI core
#
# CryptProtectData / CryptUnprotectData via ctypes — the same
# explicit-signature discipline as Phase 8 (pointer-sized members,
# no default c_int truncation).


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi_protect(data: bytes, description: str) -> bytes:
    if not _dpapi_available():
        raise VaultError(
            f"DPAPI requires win32 (this runtime is {sys.platform}) — "
            "storing secrets is refused rather than downgraded"
        )
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        description,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise VaultError(
            f"CryptProtectData failed (GetLastError={kernel32.GetLastError()})"
        )
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbSize)
    finally:
        kernel32.LocalFree(blob_out.pbData)  # type: ignore[arg-type]


def _dpapi_unprotect(data: bytes) -> bytes:
    if not _dpapi_available():
        raise VaultError(f"DPAPI requires win32 (this runtime is {sys.platform})")
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise VaultError(
            f"CryptUnprotectData failed (GetLastError={kernel32.GetLastError()}) "
            "— the vault may belong to another user or machine"
        )
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbSize)
    finally:
        kernel32.LocalFree(blob_out.pbData)  # type: ignore[arg-type]


# ------------------------------------------------------------------ vault


class BrowserVault:
    """The §11.5 credential vault — DPAPI at rest, references at the
    tool seam, redaction as the last line.

    The on-disk shape (JSON): ``{"version": 1, "entries": [{"site":
    ..., "username": ..., "secret": <base64 dpapi-blob>}]}`` — the
    secrets column is unreadable off the operator's own user+machine
    context, which is exactly the DPAPI contract.
    """

    VERSION = 1

    def __init__(self, data_root: Path | str) -> None:
        self._path = Path(data_root) / "browser" / "vault.bin"
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------ storage

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if int(raw.get("version", 0)) != self.VERSION:
                raise VaultError("unknown vault version — refusing")
            self._entries = {
                str(entry["site"]): dict(entry)
                for entry in raw.get("entries", [])
            }
        except (OSError, ValueError) as exc:
            raise VaultError(f"vault unreadable: {exc}") from exc

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "entries": list(self._entries.values()),
        }
        # atomic write (the Phase-1 persistence discipline)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tmp.replace(self._path)

    # ------------------------------------------------------------- public

    @property
    def path(self) -> str:
        return str(self._path)

    def store_from_file(self, site: str, username: str, path: str) -> dict[str, Any]:
        """Store a secret read from a file (the path rides events;
        the content never does)."""
        secret = Path(path).read_text(encoding="utf-8").strip()
        if not secret:
            raise VaultError(f"secret file {path!r} is empty")
        return self._store(site, username, secret)

    def store_from_env(self, site: str, username: str, variable: str) -> dict[str, Any]:
        """Store a secret read from an environment variable (only the
        variable name rides events)."""
        secret = os.environ.get(variable, "").strip()
        if not secret:
            raise VaultError(f"environment variable {variable!r} is unset/empty")
        return self._store(site, username, secret)

    def _store(self, site: str, username: str, secret: str) -> dict[str, Any]:
        if not site or not username:
            raise VaultError("site and username are required")
        if existing := self._entries.get(site):
            _ = existing
        cipher = _dpapi_protect(
            secret.encode("utf-8"), f"NEXUS browser vault · {site}"
        )
        self._entries[site] = {
            "site": site,
            "username": username,
            "secret": base64.b64encode(cipher).decode("ascii"),
        }
        self._save()
        logger.info("vault entry stored for site=%s username=%s", site, username)
        return {"site": site, "username": username, "stored": True}

    def issue(self, site: str) -> tuple[str, str]:
        """(username, secret) — for the engine seam ONLY.

        The caller contract: the returned secret goes into the page,
        never into tool outputs, logs, events, or memory. This method
        is deliberately not exposed as a tool operation.
        """
        entry = self._entries.get(site)
        if entry is None:
            raise VaultError(f"no vault entry for site {site!r}")
        cipher = base64.b64decode(entry["secret"])
        secret = _dpapi_unprotect(cipher).decode("utf-8")
        return str(entry["username"]), secret

    def forget(self, site: str) -> bool:
        if site not in self._entries:
            return False
        del self._entries[site]
        self._save()
        return True

    def list(self) -> list[dict[str, Any]]:
        """Site + username only — the listing an agent may see."""
        return [
            {"site": entry["site"], "username": entry["username"]}
            for entry in self._entries.values()
        ]

    # ----------------------------------------------------------- redaction

    def known_secrets(self) -> tuple[str, ...]:
        """Decrypt all secrets for the redaction pass (transient —
        the plaintext lives only in this process, never persisted,
        never logged, never evented)."""
        values: list[str] = []
        for entry in self._entries.values():
            try:
                cipher = base64.b64decode(entry["secret"])
                values.append(_dpapi_unprotect(cipher).decode("utf-8"))
            except VaultError:
                continue  # an unreadable entry is skipped, not fatal
        return tuple(values)

    def redact(self, text: str) -> str:
        """Scrub any echo of a known secret (defense in depth)."""
        for secret in self.known_secrets():
            if secret and secret in text:
                text = text.replace(secret, REDACTED)
        return text


def redact_text(text: str, secrets: tuple[str, ...]) -> str:
    """The pure scrubber (vault-free) — CI-testable anywhere."""
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, REDACTED)
    return text


__all__ = [
    "BrowserVault",
    "REDACTED",
    "VaultError",
    "redact_text",
]
