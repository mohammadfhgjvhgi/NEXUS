"""NEXUS Scope Engine package (Final Build Plan §3.2–§3.4).

The scope is the logical/policy boundary of a task — six dimensions
(§3.2), resolved from natural language (§3.3), with cross-workspace
access that is scoped and audited, never an absolute block (§3.4).
"""

from .engine import (
    KEYWORD_ASSOCIATIONS,
    CrossWorkspaceAccess,
    ScopeEngine,
    ScopeResolution,
    keywords_for,
    path_tokens,
)
from .models import (
    ALL,
    SCOPE_DIMENSIONS,
    Scope,
    host_matches,
)

__all__ = [
    "ALL",
    "KEYWORD_ASSOCIATIONS",
    "SCOPE_DIMENSIONS",
    "CrossWorkspaceAccess",
    "Scope",
    "ScopeEngine",
    "ScopeResolution",
    "host_matches",
    "keywords_for",
    "path_tokens",
]
