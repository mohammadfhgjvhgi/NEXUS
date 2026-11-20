"""Environment resolution (Final Build Plan §2.1).

Resolution order for every configuration key:

    built-in defaults  →  TOML file (config/<section>/<section>.toml)  →
    environment variable  →  typed & validated

Environment variables use the prefix ``NEXUS_`` with double-underscore
nesting::

    NEXUS_SYSTEM__DEBUG=true        → system.debug = True
    NEXUS_MODELS__CONTEXT_SIZE=4096 → models.context_size = 4096
    NEXUS_SECURITY__REDACT_SECRETS=no → security.redact_secrets = False

Values are parsed as bool / int / float / JSON when possible, otherwise
kept as strings. Single-underscore variables (``NEXUS_HOME``,
``NEXUS_TASKS_DIR`` …) are path overrides handled by :mod:`.paths`.

حل البيئة — متغيرات NEXUS_* تتغلب على الملفات، والملفات تتغلب على الافتراضي.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from .schema import SECTION_NAMES

ENV_PREFIX = "NEXUS_"
ENV_NESTING_SEPARATOR = "__"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def parse_env_value(raw: str) -> Any:
    """Parse one raw environment string into bool/int/float/JSON/str."""
    text = raw.strip()
    lowered = text.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    if text and text.lstrip("+-").isdigit():
        return int(text)
    try:
        return float(text)
    except ValueError:
        pass
    if text and text[0] in "[{":
        try:
            return json.loads(text)
        except ValueError:
            pass
    return raw


def collect_env_overrides(
    env: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Collect ``NEXUS_<SECTION>__<KEY>`` overrides into a nested mapping.

    When ``env`` is None the real process environment is used; an explicit
    mapping fully replaces it (deterministic for verification).
    """
    source = os.environ if env is None else env
    overrides: dict[str, dict[str, Any]] = {name: {} for name in SECTION_NAMES}
    for key, raw in source.items():
        if not key.startswith(ENV_PREFIX):
            continue
        body = key[len(ENV_PREFIX) :]
        if ENV_NESTING_SEPARATOR not in body:
            continue  # path variables (NEXUS_HOME, NEXUS_TASKS_DIR…) — paths.py
        section, _, key_part = body.partition(ENV_NESTING_SEPARATOR)
        section = section.lower()
        key_part = key_part.lower()
        if section not in SECTION_NAMES or not key_part:
            continue
        overrides[section][key_part] = parse_env_value(raw)
    return overrides


def deep_merge(
    base: Mapping[str, Any], override: Mapping[str, Any]
) -> dict[str, Any]:
    """Recursively merge ``override`` on top of ``base`` (override wins)."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
