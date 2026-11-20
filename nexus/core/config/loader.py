"""Configuration loading: defaults → TOML files → environment (Plan §2.1).

Each section is loaded from ``config/<section>/<section>.toml`` where the
file contains one top-level table named after its section::

    # config/system/system.toml
    [system]
    debug = true

Missing files are fine (fresh installs run on defaults). A present file
without its ``[section]`` table is reported as a warning. Environment
overrides (``NEXUS_SYSTEM__DEBUG``) win over files; provenance of every
key is recorded in ``NexusConfig.provenance``.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .environment import collect_env_overrides, deep_merge
from .paths import NexusPaths, resolve_paths
from .schema import SECTION_NAMES, ConfigError, NexusConfig


def section_file_path(config_dir: Path, section: str) -> Path:
    """Canonical location of one section's TOML file."""
    return config_dir / section / f"{section}.toml"


def load_section_file(
    config_dir: Path, section: str, warnings: list[str] | None = None
) -> dict[str, Any]:
    """Load one section's TOML table; missing file → empty mapping."""
    path = section_file_path(config_dir, section)
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config: failed to parse {path}: {exc}") from exc
    table = data.get(section)
    if table is None:
        (warnings if warnings is not None else []).append(
            f"config: {path} has no [{section}] table — ignored"
        )
        return {}
    if not isinstance(table, dict):
        raise ConfigError(f"config: [{section}] in {path} must be a table")
    return dict(table)


def load_config(
    root: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    paths: NexusPaths | None = None,
) -> NexusConfig:
    """Load the typed configuration for a runtime root.

    Resolution order per key: built-in default → file → environment.
    """
    resolved = paths if paths is not None else resolve_paths(root, env=env)
    env_overrides = collect_env_overrides(env)
    warnings: list[str] = []
    sections: dict[str, dict[str, Any]] = {}
    provenance: dict[str, str] = {}
    for section in SECTION_NAMES:
        file_values = load_section_file(resolved.config, section, warnings)
        env_values = env_overrides.get(section, {})
        sections[section] = deep_merge(file_values, env_values)
        for key in sections[section]:
            provenance[f"{section}.{key}"] = (
                "env" if key in env_values else "file"
            )
    config = NexusConfig.from_sections(sections, provenance=provenance)
    config.warnings.extend(warnings)
    return config
