"""Local paths resolution (Final Build Plan §2.1, Spec §245).

Root resolution order:

1. explicit ``root`` argument;
2. ``NEXUS_HOME`` environment variable;
3. ``~/.nexus`` (portable default).

Every runtime directory can be overridden individually
(``NEXUS_TASKS_DIR``, ``NEXUS_CONFIG_DIR`` …). All directories follow the
Spec §245 layout and are created on demand via :meth:`NexusPaths.ensure`
(including the six §2.1 config subdirectories).

حل المسارات المحلية — جذر واحد + اثنا عشر مجلدًا تشغيليًا قابلة للتجاوز.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

#: The six §2.1 config subdirectories (verbatim tree from the plan).
CONFIG_SECTION_DIRS: tuple[str, ...] = (
    "system",
    "models",
    "tools",
    "agents",
    "workspaces",
    "security",
)

DEFAULT_HOME_DIRNAME = ".nexus"

# (attribute, directory name, environment override variable)
_DIR_SPECS: tuple[tuple[str, str, str], ...] = (
    ("config", "config", "NEXUS_CONFIG_DIR"),
    ("data", "data", "NEXUS_DATA_DIR"),
    ("tasks", "tasks", "NEXUS_TASKS_DIR"),
    ("checkpoints", "checkpoints", "NEXUS_CHECKPOINTS_DIR"),
    ("logs", "logs", "NEXUS_LOGS_DIR"),
    ("memory", "memory", "NEXUS_MEMORY_DIR"),
    ("models", "models", "NEXUS_MODELS_DIR"),
    ("workspaces", "workspaces", "NEXUS_WORKSPACES_DIR"),
    ("cache", "cache", "NEXUS_CACHE_DIR"),
    ("plugins", "plugins", "NEXUS_PLUGINS_DIR"),
    ("runtime", "runtime", "NEXUS_RUNTIME_DIR"),
    ("docs", "docs", "NEXUS_DOCS_DIR"),
)


@dataclass(frozen=True, slots=True)
class NexusPaths:
    """Resolved runtime paths (Spec §245 layout)."""

    root: Path
    config: Path
    data: Path
    tasks: Path
    checkpoints: Path
    logs: Path
    memory: Path
    models: Path
    workspaces: Path
    cache: Path
    plugins: Path
    runtime: Path
    docs: Path

    @property
    def config_sections(self) -> dict[str, Path]:
        """The six §2.1 config subdirectories."""
        return {name: self.config / name for name in CONFIG_SECTION_DIRS}

    def all_dirs(self) -> tuple[Path, ...]:
        return (
            self.root,
            self.config,
            self.data,
            self.tasks,
            self.checkpoints,
            self.logs,
            self.memory,
            self.models,
            self.workspaces,
            self.cache,
            self.plugins,
            self.runtime,
            self.docs,
        )

    def ensure(self) -> NexusPaths:
        """Create every directory (idempotent); returns self."""
        for path in self.all_dirs():
            path.mkdir(parents=True, exist_ok=True)
        for section_path in self.config_sections.values():
            section_path.mkdir(parents=True, exist_ok=True)
        return self


def resolve_root(
    root: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the runtime root (argument → NEXUS_HOME → ~/.nexus)."""
    if root is not None:
        return Path(root).expanduser().absolute()
    source = os.environ if env is None else env
    home = source.get("NEXUS_HOME")
    if home:
        return Path(home).expanduser().absolute()
    return Path.home() / DEFAULT_HOME_DIRNAME


def resolve_paths(
    root: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    create: bool = False,
) -> NexusPaths:
    """Resolve all runtime paths, honoring per-directory env overrides."""
    source = os.environ if env is None else env
    root_path = resolve_root(root, source)
    kwargs: dict[str, Path] = {"root": root_path}
    for attribute, dirname, env_var in _DIR_SPECS:
        override = source.get(env_var)
        if override:
            kwargs[attribute] = Path(override).expanduser().absolute()
        else:
            kwargs[attribute] = root_path / dirname
    paths = NexusPaths(**kwargs)
    if create:
        paths.ensure()
    return paths
