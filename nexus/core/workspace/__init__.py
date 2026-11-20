"""NEXUS Workspace System package (Final Build Plan §3.1).

Owns the workspace registry: creation, unique names, persistence
(atomic JSON under ``NexusPaths.workspaces``) and path-based
resolution — the anchor of *Full Control within Task Scope*.
"""

from .manager import (
    DEFAULT_WORKSPACE_NAME,
    REGISTRY_FILENAME,
    REGISTRY_SCHEMA,
    REGISTRY_VERSION,
    WorkspaceManager,
    registry_envelope,
)
from .models import (
    DEFAULT_MEMORY_NAMESPACE,
    DEFAULT_WORKSPACE_ID,
    WORKSPACE_ID_PREFIX,
    Workspace,
    WorkspaceError,
    new_workspace_id,
    normalize_path,
    path_within,
    paths_equivalent,
)

__all__ = [
    "DEFAULT_MEMORY_NAMESPACE",
    "DEFAULT_WORKSPACE_ID",
    "DEFAULT_WORKSPACE_NAME",
    "REGISTRY_FILENAME",
    "REGISTRY_SCHEMA",
    "REGISTRY_VERSION",
    "WORKSPACE_ID_PREFIX",
    "Workspace",
    "WorkspaceError",
    "WorkspaceManager",
    "new_workspace_id",
    "normalize_path",
    "path_within",
    "paths_equivalent",
    "registry_envelope",
]
