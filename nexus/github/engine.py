"""The GitHub Engine (New Plan §16.2) — eight operations, one runtime.

The §16 thesis in one class: GitHub becomes part of NEXUS's runtime.
The §16.2 vocabulary — verbatim::

    search   clone   pull   push   branch   pr   issue   release

* ``search``  — §74's discovery rung: real REST search + the quality
  filters (:class:`SearchFilters`) + the explainable score, so
  candidates arrive ordered, honest and reproducible.
* ``clone``   — the real §16.1 Git Engine clone (the network is git's
  own; NEXUS adds no credential where none is needed).
* ``pull`` / ``push`` / ``branch`` — real git operations on the cloned
  tree through the engine that owns them.
* ``issue`` / ``pr`` / ``release`` — real REST writes; each refuses
  with :class:`TokenNotAvailableError` when no §124 token reference exists
  (public reads work, writes never pretend).

Every REST error keeps its route; every event payload keeps only names
and counts — tokens, issue bodies and release bodies never enter the
§2.2 event bus (§124).

محرك GitHub — ثماني عمليات على REST الحقيقي وثنائية git الحقيقية،
والتوكن مرجع لا نص والكتابة بلا توكن ترفض لا تتظاهر.

Stdlib only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nexus.events import EventName
from nexus.git.engine import GitEngine

from .client import DEFAULT_BASE, GitHubClient
from .contracts import (
    CloneOutcome,
    GitHubError,
    IssueRecord,
    PullRequestRecord,
    ReleaseRecord,
    SearchCandidate,
    SearchFilters,
    TokenNotAvailableError,
    TokenRef,
    score_candidate,
)

_REPO_RE = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


def _require_slug(owner_repo: str) -> str:
    if not _REPO_RE.fullmatch(owner_repo.strip()):
        raise GitHubError(f"invalid owner/repo slug: {owner_repo!r}")
    return owner_repo.strip()


class GitHubEngine:
    """The §16.2 engine over one REST client + the §16.1 Git Engine."""

    source_name = "nexus.github"

    def __init__(
        self,
        *,
        client: GitHubClient | None = None,
        token_ref: TokenRef | None = None,
        bus: Any = None,
        git_cls: type[GitEngine] = GitEngine,
    ) -> None:
        self.client = client or GitHubClient(DEFAULT_BASE)
        self.token_ref = token_ref
        self._bus = bus
        self._git_cls = git_cls

    # ------------------------------------------------------------ plumbing

    def _emit(self, name: EventName, payload: dict[str, Any], ok: bool = True) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            EventName.TOOL_COMPLETED if ok else EventName.TOOL_FAILED,
            payload=payload,
            source=self.source_name,
        )

    def _require_token(self, operation: str) -> TokenRef:
        if self.token_ref is None:
            raise TokenNotAvailableError(
                f"the {operation} operation needs a credential (Spec §124: token as reference) — "
                "pass token_ref=(env|file locator) to GitHubEngine"
            )
        return self.token_ref

    # ------------------------------------------------------------- search

    def search(
        self,
        query: str,
        *,
        filters: SearchFilters | None = None,
        max_pages: int = 1,
    ) -> tuple[SearchCandidate, ...]:
        """``search`` — GitHub repository search, filtered and scored."""
        filters = filters or SearchFilters()
        params: dict[str, Any] = {
            "q": query,
            "per_page": min(max(filters.per_page, 1), 100),
            "sort": "updated",
            "order": "desc",
        }
        payload = self.client.request("GET", "/search/repositories", params=params)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        candidates: list[SearchCandidate] = []
        for item in items:
            license_info = item.get("license") or {}
            candidate = SearchCandidate(
                name=item.get("name", ""),
                owner=(item.get("owner") or {}).get("login", ""),
                url=item.get("html_url", ""),
                clone_url=item.get("clone_url") or item.get("git_url", ""),
                stars=int(item.get("stargazers_count") or 0),
                license=(license_info or {}).get("spdx_id") if license_info else None,
                pushed_at=item.get("pushed_at", ""),
                archived=bool(item.get("archived")),
                description=item.get("description") or "",
                language=item.get("language"),
            )
            if filters.exclude_archived and candidate.archived:
                continue
            if candidate.stars < filters.min_stars:
                continue
            if filters.require_license and not candidate.license:
                continue
            if filters.language and (candidate.language or "").lower() != filters.language.lower():
                continue
            if filters.pushed_after and candidate.pushed_at < filters.pushed_after:
                continue
            candidates.append(candidate)
        scored = sorted(
            candidates,
            key=lambda c: score_candidate(c, filters),
            reverse=True,
        )[: max(1, filters.max_results)]
        self._emit(EventName.TOOL_COMPLETED, {"tool": "github.search", "results": len(scored)})
        return tuple(scored)

    # -------------------------------------------------------------- clone

    def clone(
        self,
        candidate_or_url: SearchCandidate | str,
        dest: Path | str,
        *,
        depth: int | None = 1,
        branch: str | None = None,
    ) -> CloneOutcome:
        """``clone`` — a real git clone (public repos need no credential)."""
        url = (
            candidate_or_url.clone_url
            if isinstance(candidate_or_url, SearchCandidate)
            else str(candidate_or_url)
        )
        engine = self._git_cls.clone(url, dest, depth=depth, branch=branch, bus=self._bus)
        head = engine.head()
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "github.clone", "path": str(dest), "sha": head[:12]},
        )
        return CloneOutcome(path=str(Path(dest).resolve()), url=url, commit=head, depth=depth)

    # --------------------------------------------------------- pull/push/branch

    def pull(
        self, repo_path: Path | str, *, remote: str = "origin", branch: str | None = None
    ) -> str:
        """``pull`` — fast-forward the local tree from its remote."""
        engine = self._git_cls(repo_path, bus=self._bus)
        sha = engine.pull(remote=remote, branch=branch)
        self._emit(
            EventName.TOOL_COMPLETED,
            {"tool": "github.pull", "path": str(repo_path), "sha": sha[:12]},
        )
        return sha

    def push(
        self,
        repo_path: Path | str,
        *,
        remote: str = "origin",
        branch: str | None = None,
        set_upstream: bool = True,
    ) -> str:
        """``push`` — publish local commits; the remote decides, NEXUS reports."""
        engine = self._git_cls(repo_path, bus=self._bus)
        target = engine.push(remote=remote, branch=branch, set_upstream=set_upstream)
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "github.push", "branch": target, "remote": remote}
        )
        return target

    def branch(
        self, repo_path: Path | str, name: str, *, push: bool = False, from_ref: str | None = None
    ) -> str:
        """``branch`` — a real feature branch (optionally pushed upstream)."""
        engine = self._git_cls(repo_path, bus=self._bus)
        engine.create_branch(name, checkout=True, from_ref=from_ref)
        if push:
            self.push(repo_path, branch=name)
        self._emit(EventName.TOOL_COMPLETED, {"tool": "github.branch", "branch": name})
        return name

    # --------------------------------------------------------------- issue

    def create_issue(
        self, owner_repo: str, *, title: str, body: str = "", labels: list[str] | None = None
    ) -> IssueRecord:
        """``issue`` — open an issue (needs a §124 token reference)."""
        slug = _require_slug(owner_repo)
        token_ref = self._require_token("issue")
        payload = self.client.request(
            "POST",
            f"/repos/{slug}/issues",
            body={"title": title, "body": body, "labels": labels or []},
            token_ref=token_ref,
        )
        record = IssueRecord(
            number=int(payload.get("number", 0)),
            title=payload.get("title", title),
            state=payload.get("state", "open"),
            url=payload.get("html_url", ""),
            body=payload.get("body") or "",
            labels=tuple(lbl.get("name", "") for lbl in payload.get("labels", [])),
        )
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "github.issue.create", "number": record.number}
        )
        return record

    def list_issues(
        self, owner_repo: str, *, state: str = "open", per_page: int = 30
    ) -> tuple[IssueRecord, ...]:
        """``issue`` (read) — public works without a token."""
        slug = _require_slug(owner_repo)
        items = self.client.request(
            "GET",
            f"/repos/{slug}/issues",
            params={"state": state, "per_page": min(per_page, 100)},
        )
        records = tuple(
            IssueRecord(
                number=int(i.get("number", 0)),
                title=i.get("title", ""),
                state=i.get("state", "open"),
                url=i.get("html_url", ""),
                body=i.get("body") or "",
                labels=tuple(lbl.get("name", "") for lbl in i.get("labels", [])),
            )
            for i in items
            if "pull_request" not in i  # the issues API also returns PRs — filter honestly
        )
        self._emit(EventName.TOOL_COMPLETED, {"tool": "github.issue.list", "count": len(records)})
        return records

    # ------------------------------------------------------------------ pr

    def create_pull(
        self,
        owner_repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = False,
    ) -> PullRequestRecord:
        """``pr`` — open a pull request (needs a §124 token reference)."""
        slug = _require_slug(owner_repo)
        token_ref = self._require_token("pr")
        payload = self.client.request(
            "POST",
            f"/repos/{slug}/pulls",
            body={"title": title, "head": head, "base": base, "body": body, "draft": draft},
            token_ref=token_ref,
        )
        record = PullRequestRecord(
            number=int(payload.get("number", 0)),
            title=payload.get("title", title),
            state=payload.get("state", "open"),
            head=payload.get("head", {}).get("ref", head),
            base=payload.get("base", {}).get("ref", base),
            url=payload.get("html_url", ""),
            draft=bool(payload.get("draft", draft)),
            body=payload.get("body") or "",
        )
        self._emit(EventName.TOOL_COMPLETED, {"tool": "github.pr.create", "number": record.number})
        return record

    def list_pulls(
        self, owner_repo: str, *, state: str = "open", per_page: int = 30
    ) -> tuple[PullRequestRecord, ...]:
        """``pr`` (read) — public works without a token."""
        slug = _require_slug(owner_repo)
        items = self.client.request(
            "GET",
            f"/repos/{slug}/pulls",
            params={"state": state, "per_page": min(per_page, 100)},
        )
        records = tuple(
            PullRequestRecord(
                number=int(i.get("number", 0)),
                title=i.get("title", ""),
                state=i.get("state", "open"),
                head=(i.get("head") or {}).get("ref", ""),
                base=(i.get("base") or {}).get("ref", ""),
                url=i.get("html_url", ""),
                draft=bool(i.get("draft")),
                body=i.get("body") or "",
            )
            for i in items
        )
        self._emit(EventName.TOOL_COMPLETED, {"tool": "github.pr.list", "count": len(records)})
        return records

    # ------------------------------------------------------------- release

    def create_release(
        self,
        owner_repo: str,
        *,
        tag_name: str,
        name: str,
        body: str = "",
        draft: bool = False,
        prerelease: bool = False,
    ) -> ReleaseRecord:
        """``release`` — publish a release for an existing tag (token needed)."""
        slug = _require_slug(owner_repo)
        token_ref = self._require_token("release")
        payload = self.client.request(
            "POST",
            f"/repos/{slug}/releases",
            body={
                "tag_name": tag_name,
                "name": name,
                "body": body,
                "draft": draft,
                "prerelease": prerelease,
            },
            token_ref=token_ref,
        )
        record = ReleaseRecord(
            tag_name=payload.get("tag_name", tag_name),
            name=payload.get("name", name),
            draft=bool(payload.get("draft", draft)),
            prerelease=bool(payload.get("prerelease", prerelease)),
            url=payload.get("html_url", ""),
            body=payload.get("body") or "",
        )
        self._emit(
            EventName.TOOL_COMPLETED, {"tool": "github.release.create", "tag": record.tag_name}
        )
        return record

    def list_releases(self, owner_repo: str, *, per_page: int = 10) -> tuple[ReleaseRecord, ...]:
        """``release`` (read) — public works without a token."""
        slug = _require_slug(owner_repo)
        items = self.client.request(
            "GET",
            f"/repos/{slug}/releases",
            params={"per_page": min(per_page, 100)},
        )
        records = tuple(
            ReleaseRecord(
                tag_name=i.get("tag_name", ""),
                name=i.get("name") or i.get("tag_name", ""),
                draft=bool(i.get("draft")),
                prerelease=bool(i.get("prerelease")),
                url=i.get("html_url", ""),
                body=i.get("body") or "",
            )
            for i in items
        )
        self._emit(EventName.TOOL_COMPLETED, {"tool": "github.release.list", "count": len(records)})
        return records
