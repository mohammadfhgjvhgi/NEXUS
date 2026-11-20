"""NEXUS GitHub Engine package (New Plan §16 — PHASE 16).

=========================  =======================================  ==================
Component                  Plan source                              Module
=========================  =======================================  ==================
GitHub Engine (8 ops)      §16.2 (search · clone · pull · push ·    contracts · engine
                           branch · pr · issue · release)
REST client                Spec §199 (stdlib urllib, honest 404/    client
                           rate-limit, §124 token masking)
Token reference            Spec §124 (credential as reference —     contracts.TokenRef
                           never in chat/memory/activity/output)
=========================  =======================================  ==================

The engine speaks the real REST surface through a stdlib client and
drives real git operations through the §16.1 engine.  Without a token
reference, public reads work and every write refuses with
``TokenNotAvailableError`` — NEXUS never pretends.  The token lives as a
*reference* (env var name or file path), resolved per call, masked in
every error and every event payload (§124).

محرك GitHub — جزء من runtime لا مخزن، والتوكن مرجع لا نص.

Stdlib only.
"""

from .client import DEFAULT_BASE, GitHubClient
from .contracts import (
    GITHUB_OPERATIONS,
    CloneOutcome,
    GitHubError,
    GitHubOperationKind,
    IssueRecord,
    NotFoundError,
    PullRequestRecord,
    RateLimitExceededError,
    ReleaseRecord,
    SearchCandidate,
    SearchFilters,
    TokenNotAvailableError,
    TokenRef,
    score_candidate,
    token_ref_from_env,
    token_ref_from_file,
)
from .engine import GitHubEngine

__all__ = [
    "DEFAULT_BASE",
    "GITHUB_OPERATIONS",
    "CloneOutcome",
    "GitHubClient",
    "GitHubEngine",
    "GitHubError",
    "GitHubOperationKind",
    "IssueRecord",
    "NotFoundError",
    "PullRequestRecord",
    "RateLimitExceededError",
    "ReleaseRecord",
    "SearchCandidate",
    "SearchFilters",
    "TokenNotAvailableError",
    "TokenRef",
    "score_candidate",
    "token_ref_from_env",
    "token_ref_from_file",
]
