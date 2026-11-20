"""GitHub-engine contracts (New Plan §16.2 · Spec §122/§124/§199).

The §16.2 vocabulary — eight operations, verbatim::

    search   clone   pull   push   branch   pr   issue   release

(the Spec §199 spelling — ``search | repo | clone | issues |
pullRequests | releases | push`` — is the same surface, one-to-one).

§124 fixes the token law: the credential is stored locally and handled
as a *reference*, never as text.  It must never appear in chat, memory,
activity, tool output or screenshots — so :class:`TokenRef` carries
only a locator (env var name or file path), resolves it on demand, and
its ``repr`` is always masked.  Errors and payloads carry the *name*
of the reference, never its value.

NEXUS owns the GitHub semantics (Plan §61): the engine speaks REST
through a stdlib client (urllib — no SDK), drives the real git binary
for clone/pull/push/branch via the §16.1 Git Engine, and reports the
absence of a token honestly — public reads work, writes refuse with
``TokenNotAvailableError`` instead of pretending.

عقود محرك GitHub — ثماني عمليات، والتوكن مرجع لا نص، وغيابه يُعلن
بصدق: القراءة العامة تعمل والكتابة ترفض لا تتظاهر.

Stdlib only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from nexus.git.contracts import GitEngineError

# ------------------------------------------------------------- §16.2 kinds


class GitHubError(GitEngineError):
    """GitHub-engine misuse or operation failure."""


class TokenNotAvailableError(GitHubError):
    """No usable credential — writes refuse honestly, reads may proceed."""


class RateLimitExceededError(GitHubError):
    """GitHub's rate limit — carries the reset epoch for honest backoff."""

    def __init__(self, message: str, *, reset_epoch: int | None = None) -> None:
        super().__init__(message)
        self.reset_epoch = reset_epoch


class NotFoundError(GitHubError):
    """404 from the REST surface — the repo/issue/release does not exist."""


#: §16.2 — the eight operations, verbatim.
GITHUB_OPERATIONS: tuple[str, ...] = (
    "search",
    "clone",
    "pull",
    "push",
    "branch",
    "pr",
    "issue",
    "release",
)


class GitHubOperationKind(Enum):
    """The §16.2 operation vocabulary — exactly eight members."""

    SEARCH = "search"
    CLONE = "clone"
    PULL = "pull"
    PUSH = "push"
    BRANCH = "branch"
    PR = "pr"
    ISSUE = "issue"
    RELEASE = "release"

    @classmethod
    def from_value(cls, value: str | GitHubOperationKind) -> GitHubOperationKind:
        """Coerce a plan name (any case) or member into the member."""
        if isinstance(value, cls):
            return value
        name = str(value).strip().lower()
        aliases = {"pullrequests": "pr", "pull_request": "pr", "pullrequest": "pr"}
        name = aliases.get(name.replace(" ", "_").replace("-", "_"), name)
        for member in cls:
            if member.value == name:
                return member
        raise GitHubError(f"unknown github operation: {value!r}")


# ---------------------------------------------------------------- token §124


class TokenRef:
    """A credential *reference* — §124's law made type-safe.

    Two locators only:

    * ``("env", "NEXUS_GITHUB_TOKEN")``  — read from the environment;
    * ``("file", "M:/NEXUS/.vault/gh.token")`` — read from a local file.

    The resolved value exists only inside :meth:`resolve`'s caller frame;
    ``repr``/``str`` always show the locator, never the secret.
    """

    __slots__ = ("kind", "locator")

    def __init__(self, kind: str, locator: str) -> None:
        if kind not in ("env", "file"):
            raise GitHubError(f"token kind must be 'env' or 'file', got {kind!r}")
        if not locator:
            raise GitHubError("token locator must be non-empty")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "locator", locator)

    def __repr__(self) -> str:  # §124 — never the value, always the locator
        return f"TokenRef(kind={self.kind!r}, locator={self.locator!r})"

    __str__ = __repr__

    def describe(self) -> dict[str, str]:
        """Payload-safe description — safe for events, logs, chat."""
        return {"kind": self.kind, "locator": self.locator}

    def resolve(self) -> str:
        """Return the secret value (caller must not persist it)."""
        if self.kind == "env":
            value = os.environ.get(self.locator, "")
        else:
            try:
                value = Path(self.locator).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise TokenNotAvailableError(f"token file unreadable: {self.locator!r}") from exc
        if not value:
            raise TokenNotAvailableError(f"token reference is empty: {self!r}")
        return value


def token_ref_from_env(name: str = "NEXUS_GITHUB_TOKEN") -> TokenRef:
    """A TokenRef pointing at an environment variable (§124 pattern)."""
    return TokenRef("env", name)


def token_ref_from_file(path: str | Path) -> TokenRef:
    """A TokenRef pointing at a local file (§124 pattern)."""
    return TokenRef("file", str(path))


# ------------------------------------------------------------ result shapes


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    """One ``search`` hit — the §74 discovery rung's raw material."""

    name: str
    owner: str
    url: str
    clone_url: str
    stars: int
    license: str | None
    pushed_at: str
    archived: bool
    description: str = ""
    language: str | None = None
    score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "owner": self.owner,
            "url": self.url,
            "clone_url": self.clone_url,
            "stars": self.stars,
            "license": self.license,
            "pushed_at": self.pushed_at,
            "archived": self.archived,
            "description": self.description,
            "language": self.language,
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """§74's *Filter* rung — quality gates before a repo ever enters."""

    min_stars: int = 0
    require_license: bool = False
    exclude_archived: bool = True
    language: str | None = None
    pushed_after: str | None = None
    per_page: int = 30
    max_results: int = 30

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_stars": self.min_stars,
            "require_license": self.require_license,
            "exclude_archived": self.exclude_archived,
            "language": self.language,
            "pushed_after": self.pushed_after,
            "per_page": self.per_page,
            "max_results": self.max_results,
        }


@dataclass(frozen=True, slots=True)
class IssueRecord:
    """One ``issue`` answer."""

    number: int
    title: str
    state: str
    url: str = ""
    body: str = ""
    labels: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "state": self.state,
            "url": self.url,
            "body": self.body,
            "labels": list(self.labels),
        }


@dataclass(frozen=True, slots=True)
class PullRequestRecord:
    """One ``pr`` answer."""

    number: int
    title: str
    state: str
    head: str
    base: str
    url: str = ""
    draft: bool = False
    body: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "state": self.state,
            "head": self.head,
            "base": self.base,
            "url": self.url,
            "draft": self.draft,
            "body": self.body,
        }


@dataclass(frozen=True, slots=True)
class ReleaseRecord:
    """One ``release`` answer."""

    tag_name: str
    name: str
    draft: bool
    prerelease: bool
    url: str = ""
    body: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "tag_name": self.tag_name,
            "name": self.name,
            "draft": self.draft,
            "prerelease": self.prerelease,
            "url": self.url,
            "body": self.body,
        }


@dataclass(frozen=True, slots=True)
class CloneOutcome:
    """The ``clone`` answer — the real local path the repo now lives at."""

    path: str
    url: str
    commit: str
    depth: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "url": self.url, "commit": self.commit, "depth": self.depth}


#: The §74 scoring rung — a tiny, honest, documented preference order.
def score_candidate(candidate: SearchCandidate, filters: SearchFilters) -> float:
    """Prefer active, licensed, maintained repos — a stable, explainable score.

    stars (log-ish bands) + license present + not archived + recently
    pushed.  No ML, no secrets — just §74's *Activity → License* ladder.
    """
    score = 0.0
    score += min(candidate.stars, 10_000) / 1_000.0  # 0..10
    if candidate.license:
        score += 2.0
    if not candidate.archived:
        score += 1.0
    if candidate.pushed_at >= "2024-01-01":
        score += 1.0
    return round(score, 3)
