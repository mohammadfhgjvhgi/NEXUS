"""Source classification (New Plan §17.3) — six classes, one ladder.

Every hit lands in exactly one of the verbatim §17.3 classes::

    official   documentation   academic   community   personal   unknown

The ladder is a documented, deterministic preference order — first
match wins, ``unknown`` is the honest fallback:

1. an explicit ``metadata["nexus_class"]`` (validated, providers may
   know better than any URL rule);
2. academic — arXiv, DOI, .edu, IEEE/ACM/PubMed/publisher hosts;
3. documentation — ``docs.*``, ``developer.*``, readthedocs, an
   explicit ``/docs/`` path;
4. official — governments, standards bodies, and the vendor/project
   hosts themselves (python.org, kernel.org, microsoft.com…); a
   GitHub *repository* is its project's own home (metadata says
   ``github_type=repo``);
5. community — Reddit, Stack Overflow/Exchange, Hacker News, GitHub
   issues/discussions, Discourse forums;
6. personal — blog platforms and anything marked personal.

تصنيف المصادر — ست فئات حرفيًا وسلّم قرارات موثق؛ المجهول يبقى فئة
صادقة لا تخمينًا.

Stdlib only.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .contracts import ResearchError, SearchHit, SourceClass

#: hosts whose *purpose* is documentation — checked before official so
#: ``docs.python.org`` reads as documentation, not as python.org-official.
_DOC_HOSTS: tuple[str, ...] = (
    "readthedocs.io",
    "readthedocs.org",
    "rtfd.io",
    "readthedocs",
)

_OFFICIAL_HOSTS: tuple[str, ...] = (
    "python.org",
    "kernel.org",
    "gnu.org",
    "microsoft.com",
    "apple.com",
    "mozilla.org",
    "w3.org",
    "ietf.org",
    "rfc-editor.org",
    "iso.org",
    "openjdk.org",
    "github.com",  # a repository is its project's own home (ladder rule 4)
)

_COMMUNITY_HOSTS: tuple[str, ...] = (
    "reddit.com",
    "stackoverflow.com",
    "stackexchange.com",
    "news.ycombinator.com",
    "quora.com",
    "dev.to",
    "discourse.org",
    "github.com",  # issues/discussions (metadata github_type decides)
)

_PERSONAL_HOSTS: tuple[str, ...] = (
    "blogspot.com",
    "wordpress.com",
    "substack.com",
    "medium.com",
    "hashnode.dev",
    "vercel.app",
    "github.io",
)

_GITHUB_TYPE_CLASS: dict[str, str] = {
    "repo": SourceClass.OFFICIAL,
    "issue": SourceClass.COMMUNITY,
    "discussion": SourceClass.COMMUNITY,
    "pull": SourceClass.COMMUNITY,
    "wiki": SourceClass.DOCUMENTATION,
}

def _host(uri: str) -> str:
    """Lowercase hostname without a leading ``www.`` (or '' for non-URLs)."""
    try:
        host = (urlparse(uri).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, entries: tuple[str, ...]) -> bool:
    return any(host == entry or host.endswith("." + entry) for entry in entries)


def classify(hit: SearchHit) -> str:
    """§17.3 — one hit → one of the six verbatim classes (ladder order)."""
    explicit = hit.metadata.get("nexus_class", "").strip().lower()
    if explicit:
        if explicit not in (SourceClass.OFFICIAL, SourceClass.DOCUMENTATION,
                            SourceClass.ACADEMIC, SourceClass.COMMUNITY,
                            SourceClass.PERSONAL, SourceClass.UNKNOWN):
            raise ResearchError(f"metadata nexus_class is not a §17.3 class: {explicit!r}")
        return explicit

    github_type = hit.metadata.get("github_type", "").strip().lower()
    if github_type in _GITHUB_TYPE_CLASS:
        return _GITHUB_TYPE_CLASS[github_type]

    host = _host(hit.uri)
    path = urlparse(hit.uri).path.lower()

    if not host:
        if hit.uri.startswith("file:"):
            docs_hint = "/docs/" in path or "\\docs\\" in path or ".md" in path
            return SourceClass.DOCUMENTATION if docs_hint else SourceClass.UNKNOWN
        return SourceClass.UNKNOWN

    # 2 — academic
    if (
        _host_matches(host, ("arxiv.org", "doi.org", "ieee.org", "acm.org",
                             "pubmed.ncbi.nlm.nih.gov", "nature.com", "science.org",
                             "springer.com", "sciencedirect.com", "semanticscholar.org",
                             "scholar.google.com"))
        or host.endswith(".edu")
        or host.endswith(".ac.uk")
    ):
        return SourceClass.ACADEMIC

    # 3 — documentation (before official: docs.python.org is documentation)
    if (
        host.startswith("docs.")
        or host.startswith("developer.")
        or host.startswith("wiki.")
        or ".readthedocs." in host
        or _host_matches(host, _DOC_HOSTS)
        or "/docs/" in path
        or path.endswith((".md", ".rst"))
    ):
        return SourceClass.DOCUMENTATION

    # 5 — community before official: github issues live on github.com too
    if _host_matches(host, ("reddit.com", "stackoverflow.com", "stackexchange.com",
                            "news.ycombinator.com", "quora.com", "dev.to")):
        return SourceClass.COMMUNITY

    # 4 — official
    if _host_matches(host, _OFFICIAL_HOSTS) or host.endswith(".gov") or ".gov." in host:
        return SourceClass.OFFICIAL

    # 6 — personal
    if _host_matches(host, _PERSONAL_HOSTS) or host.startswith("blog."):
        return SourceClass.PERSONAL

    # forums by path shape (a Discourse on its own domain)
    if "/t/" in path or "/forum" in path:
        return SourceClass.COMMUNITY

    return SourceClass.UNKNOWN
