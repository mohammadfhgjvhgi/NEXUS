"""Rule sets (Final Build Plan §7.1 — the ECC rules pattern, adapted).

ECC organizes behavioral rules as small markdown documents grouped by
topic (languages, common, security). NEXUS adapts the *pattern*: a
rule is a titled instruction with a priority and a scope tag; the
harness compiles the enabled rules into one deterministic context
section the model receives on every turn (the §41 contract: "Rules").

Layout::

    <root>/rules/<rule-id>/RULE.md
    <root>/rules/<rule-id>.md

A RULE.md looks like::

    ---
    title: Never delete files outside the workspace
    priority: 100
    scope: security
    ---

    The agent must refuse any request to delete ...

``priority`` (0–100, higher wins) orders the section; ``scope`` tags
rules into groups (``common`` / ``security`` / …) so callers can
curate what ships. Rules load at boot; a malformed file is skipped
with a warning — never a boot failure.

Stdlib only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("nexus.harness")

#: The §7.1 rule record fields (harness-provable).
RULE_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "body",
    "priority",
    "scope",
    "enabled",
)

_RULE_SECTION_HEADER = "RULES (binding, by priority)"

_FRONTMATTER_FENCE = re.compile(r"^---\s*$")
_KEY_LINE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$")

#: The ECC security scope tag, carried verbatim as the curation hook.
SECURITY_SCOPE = "security"


@dataclass(slots=True)
class Rule:
    """One behavioral rule (the ECC rules pattern, NEXUS-owned shape)."""

    id: str
    title: str
    body: str = ""
    priority: int = 50
    scope: str = "common"
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("rule.id must be non-empty")
        if not self.title:
            raise ValueError(f"rule {self.id}: title must be non-empty")
        self.priority = max(0, min(100, int(self.priority)))

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "priority": str(self.priority),
            "scope": self.scope,
            "enabled": str(self.enabled),
        }

    def context_block(self) -> str:
        """Render this rule as one numbered context block."""
        body = self.body.strip()
        head = f"[P{self.priority:03d}] {self.title}"
        return f"{head}\n{body}" if body else head


@dataclass(slots=True)
class RuleSet:
    """The rule registry for one NEXUS root (Plan §7.1 pattern)."""

    root: Path
    rules: dict[str, Rule] = field(default_factory=dict)

    # ------------------------------------------------------------- loading

    @classmethod
    def load(cls, root: str | Path) -> RuleSet:
        """Load every RULE.md under ``root`` (missing dir → empty)."""
        directory = Path(root)
        rule_set = cls(root=directory)
        if not directory.is_dir():
            return rule_set
        for path in sorted(directory.iterdir()):
            rule = _load_rule_path(path)
            if rule is not None:
                rule_set.rules[rule.id] = rule
        logger.info("rule set loaded %d rule(s) from %s", len(rule_set.rules), directory)
        return rule_set

    # ------------------------------------------------------------- queries

    def list(self) -> list[Rule]:
        """All rules, highest priority first (the compile order)."""
        return sorted(self.rules.values(), key=lambda r: (-r.priority, r.id))

    def get(self, rule_id: str) -> Rule | None:
        return self.rules.get(rule_id)

    def by_scope(self, scope: str) -> list[Rule]:
        return [r for r in self.list() if r.scope == scope]

    def security_rules(self) -> list[Rule]:
        """The ECC security subset — what every prompt must carry."""
        return self.by_scope(SECURITY_SCOPE)

    # ------------------------------------------------------------- roster

    def add(self, rule: Rule) -> None:
        self.rules[rule.id] = rule

    def remove(self, rule_id: str) -> bool:
        return self.rules.pop(rule_id, None) is not None

    # ------------------------------------------------------------- context

    def context_section(self, *, scopes: tuple[str, ...] | None = None,
                        limit: int = 12) -> str:
        """The §41 context contribution: the compiled rule section.

        ``scopes`` curates which scope tags ship (``None`` → all).
        The section is empty when no enabled rule matches — rules are
        opt-in content, not boilerplate.
        """
        chosen: list[Rule] = [
            rule
            for rule in self.list()
            if rule.enabled and (scopes is None or rule.scope in scopes)
        ]
        chosen = chosen[: max(0, limit)]
        if not chosen:
            return ""
        blocks = [_RULE_SECTION_HEADER]
        blocks.extend(rule.context_block() for rule in chosen)
        return "\n".join(blocks)


def _load_rule_path(path: Path) -> Rule | None:
    """Load one rule from a directory (RULE.md) or a flat file."""
    if path.is_dir():
        candidate = path / "RULE.md"
        if not candidate.is_file():
            return None
        rule_id = path.name
        file_path = candidate
    elif path.is_file() and path.suffix.lower() == ".md":
        rule_id = path.stem
        file_path = path
    else:
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("rule %s unreadable (%s) — skipped", file_path, exc)
        return None
    header, body = _split_frontmatter(text)
    title = header.get("title") or rule_id.replace("-", " ").replace("_", " ").strip()
    try:
        priority = int(header.get("priority", "50"))
    except ValueError:
        priority = 50
    rule = Rule(
        id=rule_id,
        title=title,
        body=body,
        priority=priority,
        scope=header.get("scope", "common"),
        enabled=header.get("enabled", "true").strip().casefold()
        not in {"false", "0", "no"},
    )
    return rule


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Same frontmatter contract as skills (shared subset parser)."""
    lines = text.splitlines()
    if not lines or not _FRONTMATTER_FENCE.match(lines[0].strip()):
        return {}, text
    header: dict[str, str] = {}
    for index in range(1, len(lines)):
        line = lines[index].strip()
        if _FRONTMATTER_FENCE.match(line):
            body = "\n".join(lines[index + 1 :]).strip()
            return header, body
        match = _KEY_LINE.match(line)
        if match:
            header[match.group(1).strip()] = match.group(2).strip()
    return {}, text
