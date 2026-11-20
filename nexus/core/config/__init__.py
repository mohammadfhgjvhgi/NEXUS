"""NEXUS Core Configuration package (Final Build Plan §2.1).

typed configuration · environment resolution · local paths ·
runtime configuration.
"""

from .environment import (
    collect_env_overrides,
    deep_merge,
    parse_env_value,
)
from .loader import load_config, load_section_file, section_file_path
from .paths import (
    CONFIG_SECTION_DIRS,
    NexusPaths,
    resolve_paths,
    resolve_root,
)
from .runtime import NexusRuntime
from .schema import (
    SECTION_NAMES,
    AgentsConfig,
    ConfigError,
    ModelsConfig,
    NexusConfig,
    SecurityConfig,
    SystemConfig,
    ToolsConfig,
    WorkspacesConfig,
    build_section,
)

__all__ = [
    "CONFIG_SECTION_DIRS",
    "SECTION_NAMES",
    "AgentsConfig",
    "ConfigError",
    "ModelsConfig",
    "NexusConfig",
    "NexusPaths",
    "NexusRuntime",
    "SecurityConfig",
    "SystemConfig",
    "ToolsConfig",
    "WorkspacesConfig",
    "build_section",
    "collect_env_overrides",
    "deep_merge",
    "load_config",
    "load_section_file",
    "parse_env_value",
    "resolve_paths",
    "resolve_root",
    "section_file_path",
]
