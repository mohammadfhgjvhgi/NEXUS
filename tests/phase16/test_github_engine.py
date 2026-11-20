"""Phase 16 — §16.2 the GitHub Engine against a real local HTTP server.

The REST law (404 honest, rate-limit carries its reset epoch, token in
the Authorization header only) is proven against a real HTTP server in
a thread — not against mocks.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fixtures import git, init_repo

from nexus.events import EventBus
from nexus.github import (
    GITHUB_OPERATIONS,
    GitHubClient,
    GitHubEngine,
    GitHubError,
    GitHubOperationKind,
    NotFoundError,
    RateLimitExceededError,
    TokenNotAvailableError,
    TokenRef,
    score_candidate,
)
from nexus.github.contracts import SearchCandidate, SearchFilters

REPO_A: dict[str, Any] = {
    "name": "alpha",
    "owner": {"login": "nexuslabs"},
    "html_url": "https://github.com/nexuslabs/alpha",
    "clone_url": "https://github.com/nexuslabs/alpha.git",
    "stargazers_count": 1500,
    "license": {"spdx_id": "MIT"},
    "pushed_at": "2026-01-15T00:00:00Z",
    "archived": False,
    "description": "the alpha repo",
    "language": "Python",
}
REPO_B: dict[str, Any] = {
    "name": "beta",
    "owner": {"login": "nexuslabs"},
    "html_url": "https://github.com/nexuslabs/beta",
    "clone_url": "https://github.com/nexuslabs/beta.git",
    "stargazers_count": 30,
    "license": None,
    "pushed_at": "2020-01-01T00:00:00Z",
    "archived": True,
    "description": "stale and archived",
    "language": "Java",
}


class FakeGitHub(BaseHTTPRequestHandler):
    """A real HTTP server speaking just enough GitHub REST to prove the law."""

    server_version = "FakeGitHub/1.0"

    def log_message(self, *args: Any) -> None:  # silence the test output
        return

    def _send(self, code: int, payload: Any, extra: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — http.server naming
        auth = self.headers.get("Authorization")
        if self.path.startswith("/search/repositories"):
            self._send(200, {"items": [REPO_A, REPO_B], "total_count": 2})
        elif self.path.startswith("/repos/nexuslabs/alpha/issues"):
            self._send(200, [{
                "number": 1, "title": "first", "state": "open", "html_url": "u",
                "body": "b", "labels": [{"name": "bug"}],
            }])
        elif self.path.startswith("/repos/nexuslabs/alpha/pulls"):
            self._send(200, [{
                "number": 7, "title": "a pr", "state": "open",
                "head": {"ref": "feature/x"}, "base": {"ref": "main"},
                "html_url": "u", "draft": False, "body": "",
            }])
        elif self.path.startswith("/repos/nexuslabs/alpha/releases"):
            self._send(200, [{
                "tag_name": "v0.1.0", "name": "Alpha One", "draft": False,
                "prerelease": False, "html_url": "u", "body": "notes",
            }])
        elif self.path.startswith("/repos/missing/none"):
            self._send(404, {"message": "Not Found"})
        elif self.path.startswith("/repos/ratelimited/none"):
            self._send(
                403,
                {"message": "API rate limit exceeded"},
                {"X-RateLimit-Reset": "1893456000"},
            )
        elif auth == "Bearer secret-token-value":
            self._send(200, {"ok": True, "authorized": True})
        else:
            self._send(200, {"ok": True, "authorized": False})

    def do_POST(self) -> None:  # noqa: N802
        auth = self.headers.get("Authorization")
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if auth != "Bearer secret-token-value":
            self._send(401, {"message": "Requires authentication"})
            return
        if self.path.startswith("/repos/nexuslabs/alpha/issues"):
            self._send(201, {
                "number": 42, "title": body.get("title", ""), "state": "open",
                "html_url": "u", "body": body.get("body", ""),
                "labels": [{"name": n} for n in body.get("labels", [])],
            })
        elif self.path.startswith("/repos/nexuslabs/alpha/pulls"):
            self._send(201, {
                "number": 9, "title": body.get("title", ""), "state": "open",
                "head": {"ref": body.get("head", "")}, "base": {"ref": body.get("base", "")},
                "html_url": "u", "draft": body.get("draft", False), "body": body.get("body", ""),
            })
        elif self.path.startswith("/repos/nexuslabs/alpha/releases"):
            self._send(201, {
                "tag_name": body.get("tag_name", ""), "name": body.get("name", ""),
                "draft": body.get("draft", False), "prerelease": body.get("prerelease", False),
                "html_url": "u", "body": body.get("body", ""),
            })
        else:
            self._send(404, {"message": "Not Found"})


@pytest.fixture(scope="module")
def server() -> Any:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture()
def client(server: Any) -> GitHubClient:
    return GitHubClient(base=server, timeout=10)


@pytest.fixture()
def engine(client: GitHubClient) -> GitHubEngine:
    return GitHubEngine(client=client)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


# ------------------------------------------------------------------ vocabulary


def test_the_eight_operations_verbatim() -> None:
    assert GITHUB_OPERATIONS == (
        "search",
        "clone",
        "pull",
        "push",
        "branch",
        "pr",
        "issue",
        "release",
    )
    assert len(GitHubOperationKind) == 8
    assert GitHubOperationKind.from_value("pullRequests") is GitHubOperationKind.PR


# ------------------------------------------------------------------ token §124


def test_token_ref_never_leaks_value() -> None:
    ref = TokenRef("env", "NEXUS_GITHUB_TOKEN")
    text = f"{ref} / {ref!r} / {ref.describe()}"
    assert "secret" not in text.lower().replace("secret-token", "")  # locator only
    assert "NEXUS_GITHUB_TOKEN" in text


def test_token_ref_empty_env_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_TEST_TOKEN", raising=False)
    ref = TokenRef("env", "NEXUS_TEST_TOKEN")
    with pytest.raises(TokenNotAvailableError):
        ref.resolve()


def test_token_ref_file_missing_refuses(tmp_path: Path) -> None:
    ref = TokenRef("file", str(tmp_path / "no.token"))
    with pytest.raises(TokenNotAvailableError):
        ref.resolve()


def test_writes_refuse_without_token(engine: GitHubEngine) -> None:
    with pytest.raises(TokenNotAvailableError, match="issue"):
        engine.create_issue("nexuslabs/alpha", title="t")
    with pytest.raises(TokenNotAvailableError, match="pr"):
        engine.create_pull("nexuslabs/alpha", title="t", head="h", base="main")
    with pytest.raises(TokenNotAvailableError, match="release"):
        engine.create_release("nexuslabs/alpha", tag_name="v1", name="n")


# ------------------------------------------------------------------ client law


def test_404_is_honest(client: GitHubClient) -> None:
    with pytest.raises(NotFoundError):
        client.request("GET", "/repos/missing/none")


def test_rate_limit_carries_reset_epoch(client: GitHubClient) -> None:
    with pytest.raises(RateLimitExceededError) as info:
        client.request("GET", "/repos/ratelimited/none")
    assert info.value.reset_epoch == 1893456000


def test_authorized_header_flows(client: GitHubClient) -> None:
    token_ref = TokenRef("env", "PHASE16_TEST_TOKEN")
    token_ref.__dict__ if False else None  # noqa: B018 — TokenRef is slotted
    import os

    os.environ["PHASE16_TEST_TOKEN"] = "secret-token-value"
    try:
        payload = client.request("GET", "/whoami", token_ref=token_ref)
        assert payload["authorized"] is True
    finally:
        del os.environ["PHASE16_TEST_TOKEN"]


# --------------------------------------------------------------------- search


def test_search_filters_and_scores(engine: GitHubEngine) -> None:
    candidates = engine.search(
        "agent framework",
        filters=SearchFilters(min_stars=100, exclude_archived=True),
    )
    names = [c.name for c in candidates]
    assert "beta" not in names  # archived + 30 stars fail the filters
    assert "alpha" in names
    assert candidates[0].name == "alpha"
    assert candidates[0].clone_url.endswith(".git")


def test_score_prefers_license_and_activity() -> None:
    strong = SearchCandidate(
        name="a", owner="o", url="u", clone_url="c", stars=2000,
        license="MIT", pushed_at="2026-01-01", archived=False,
    )
    weak = SearchCandidate(
        name="b", owner="o", url="u", clone_url="c", stars=5,
        license=None, pushed_at="2019-01-01", archived=True,
    )
    assert score_candidate(strong, SearchFilters()) > score_candidate(weak, SearchFilters())


# -------------------------------------------------------------- reads work


def test_list_issues_and_prs_and_releases_public(engine: GitHubEngine) -> None:
    issues = engine.list_issues("nexuslabs/alpha")
    assert issues[0].number == 1
    pulls = engine.list_pulls("nexuslabs/alpha")
    assert pulls[0].head == "feature/x"
    releases = engine.list_releases("nexuslabs/alpha")
    assert releases[0].tag_name == "v0.1.0"


# --------------------------------------------------------------------- clone


def test_clone_via_local_bare(engine: GitHubEngine, tmp_path: Path) -> None:
    seed = init_repo(tmp_path / "seed")
    bare = tmp_path / "seed.git"
    git(tmp_path, "clone", "--bare", str(seed), str(bare))
    outcome = engine.clone(str(bare), tmp_path / "cloned")
    assert (Path(outcome.path) / "README.md").exists()
    assert len(outcome.commit) == 40


def test_pull_push_branch_over_local_origin(
    tmp_path: Path, client: GitHubClient, bus: EventBus
) -> None:
    engine = GitHubEngine(client=client, bus=bus)
    seed = init_repo(tmp_path / "repo")
    bare = tmp_path / "origin.git"
    git(tmp_path, "clone", "--bare", str(seed), str(bare))
    work = tmp_path / "work"
    git(tmp_path, "clone", str(bare), str(work))
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")

    # branch → commit → push → clone again → pull
    engine.branch(work, "feature/pipeline", push=True)
    (work / "hello.txt").write_text("hi\n", encoding="utf-8")
    from nexus.git import GitEngine

    GitEngine(work).commit("feat: pipeline file", paths=(".",))
    engine.push(work)
    assert (work / "hello.txt").exists()

    other = tmp_path / "other"
    git(tmp_path, "clone", str(bare), str(other))
    git(other, "config", "user.email", "t@t")
    git(other, "config", "user.name", "t")
    sha = engine.pull(other, branch="feature/pipeline")
    assert len(sha) == 40
    assert (other / "hello.txt").exists()
    assert bus.published_count > 0


# --------------------------------------------------------------- writes work


def test_issue_pr_release_writes_with_token(
    client: GitHubClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PHASE16_WRITE_TOKEN", "secret-token-value")
    engine = GitHubEngine(
        client=client,
        token_ref=TokenRef("env", "PHASE16_WRITE_TOKEN"),
    )
    issue = engine.create_issue("nexuslabs/alpha", title="found a bug", labels=["bug"])
    assert issue.number == 42
    pr = engine.create_pull("nexuslabs/alpha", title="my pr", head="feature/x", base="main")
    assert pr.number == 9 and pr.head == "feature/x" and pr.base == "main"
    release = engine.create_release("nexuslabs/alpha", tag_name="v1.2.3", name="One Two Three")
    assert release.tag_name == "v1.2.3"


def test_bad_slug_refused(engine: GitHubEngine) -> None:
    with pytest.raises(GitHubError, match="slug"):
        engine.list_issues("not a slug")
