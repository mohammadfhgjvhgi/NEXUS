"""Skill library (Final Build Plan §7.1 — the ECC skill pattern, adapted).

What ECC (``affaan-m/ecc``, MODE B) contributes to NEXUS is not code but
a **format discipline**: a skill is a small markdown document with a
frontmatter header (``name`` + ``description`` + optional metadata)
followed by an instruction body ("When to Use" / "How it Works").
NEXUS owns the loader and the shapes — nothing imports ECC.

Layout (the §41 harness contract: skills are one of the seven things
the model receives)::

    <root>/skills/<skill-id>/SKILL.md      # one skill per directory
    <root>/skills/<skill-id>.md            # or a single flat file

A SKILL.md looks like::

    ---
    name: accessibility
    description: Audit UI for WCAG 2.2 AA compliance.
    ---

    # Accessibility

    When to use: ...
    How it works: ...

The parser accepts YAML-ish frontmatter (``key: value`` lines between
``---`` fences) — the subset every skill file in the wild actually
uses. Malformed files are skipped with a warning (a bad skill must
never break the boot).

Stdlib only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("nexus.harness")

#: The §7.1 skill record fields (harness-provable).
SKILL_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "description",
    "instructions",
    "origin",
    "enabled",
)

_FRONTMATTER_FENCE = re.compile(r"^---\s*$")
_KEY_LINE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$")

#: Marker tag the context builder looks for (see harness/context.py).
_SKILL_SECTION_HEADER = "RELEVANT SKILLS"


@dataclass(slots=True)
class Skill:
    """One loaded skill (the ECC SKILL.md pattern, NEXUS-owned shape)."""

    id: str
    name: str
    description: str = ""
    instructions: str = ""
    origin: str = "local"
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("skill.id must be non-empty")
        if not self.name:
            raise ValueError(f"skill {self.id!r}: name must be non-empty")

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "origin": self.origin,
            "enabled": str(self.enabled),
        }

    # ------------------------------------------------------------ matching

    def matches(self, directive: str) -> bool:
        """Keyword match between a task directive and this skill.

        A skill matches when any significant word of its name or
        description appears in the directive (case-folded). This is a
        deliberately cheap filter — the model decides what to apply,
        the library only curates candidates.
        """
        if not self.enabled:
            return False
        haystack = directive.casefold()
        for word in _significant_words(f"{self.name} {self.description}"):
            if word in haystack:
                return True
        return False

    def context_block(self) -> str:
        """Render this skill as one context block for the model."""
        head = f"### skill: {self.name}"
        if self.description:
            head += f" — {self.description}"
        body = self.instructions.strip()
        return f"{head}\n{body}" if body else head


_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in into is it its of on "
    "or that the to use uses using was were when with you your can will "
    "must should this these those there their them then than so not no "
    "do does did done how what which who whom why where all any both "
    "each few more most other some such only own same too very just".split()
)


def _significant_words(text: str, limit: int = 24) -> list[str]:
    words: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9_+-]{2,}", text):
        token = raw.casefold().strip("+-")
        if token and token not in _STOPWORDS and len(token) >= 3:
            words.append(token)
            if len(words) >= limit:
                break
    return words


@dataclass(slots=True)
class SkillLibrary:
    """The skill registry for one NEXUS root (Plan §7.1 pattern).

    The library is loaded once from ``<root>/skills`` and stays an
    in-memory snapshot; skills change rarely and a reboot re-reads
    them. ``add``/``remove`` mutate the in-memory roster only — the
    files on disk are the source of truth.
    """

    root: Path
    skills: dict[str, Skill] = field(default_factory=dict)

    # ------------------------------------------------------------- loading

    @classmethod
    def load(cls, root: str | Path) -> SkillLibrary:
        """Load every SKILL.md under ``root`` (missing dir → empty)."""
        directory = Path(root)
        library = cls(root=directory)
        if not directory.is_dir():
            return library
        for path in sorted(directory.iterdir()):
            skill = _load_skill_path(path)
            if skill is not None:
                library.skills[skill.id] = skill
        logger.info("skill library loaded %d skill(s) from %s", len(library.skills), directory)
        return library

    # ------------------------------------------------------------- queries

    def list(self) -> list[Skill]:
        """All loaded skills, ordered by id (a stable roster)."""
        return [self.skills[key] for key in sorted(self.skills)]

    def get(self, skill_id: str) -> Skill | None:
        return self.skills.get(skill_id)

    def find(self, directive: str, *, limit: int = 4) -> list[Skill]:
        """Skills whose name/description matches the directive."""
        return [s for s in self.list() if s.matches(directive)][: max(0, limit)]

    def enabled(self) -> list[Skill]:
        return [s for s in self.list() if s.enabled]

    # ------------------------------------------------------------- roster

    def add(self, skill: Skill) -> None:
        """Register an in-memory skill (tests, programmatic use)."""
        if not skill.id:
            raise ValueError("skill.id must be non-empty")
        self.skills[skill.id] = skill

    def remove(self, skill_id: str) -> bool:
        return self.skills.pop(skill_id, None) is not None

    # ------------------------------------------------------------ context

    def context_section(self, directive: str, *, limit: int = 4) -> str:
        """The §41 context contribution: matching skills, ready to be
        appended to the model prompt. Empty when nothing matches —
        a quiet harness never adds noise."""
        chosen = self.find(directive, limit=limit)
        if not chosen:
            return ""
        blocks = [_SKILL_SECTION_HEADER]
        blocks.extend(skill.context_block() for skill in chosen)
        return "\n\n".join(blocks)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a SKILL.md into its frontmatter dict and body.

    Accepts the common shape only: the file starts with ``---`` on its
    own line and a closing ``---`` fence follows. A missing fence
    yields an empty header and the whole text as body.
    """
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


def _load_skill_path(path: Path) -> Skill | None:
    """Load one skill from a directory (SKILL.md) or a flat file."""
    if path.is_dir():
        candidate = path / "SKILL.md"
        if not candidate.is_file():
            return None
        skill_id = path.name
        file_path = candidate
    elif path.is_file() and path.suffix.lower() == ".md":
        skill_id = path.stem
        file_path = path
    else:
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:  # unreadable skill — skip, never break boot
        logger.warning("skill %s unreadable (%s) — skipped", file_path, exc)
        return None
    header, body = _parse_frontmatter(text)
    name = header.get("name") or skill_id
    description = header.get("description", "")
    origin = header.get("origin", "local")
    enabled = header.get("enabled", "true").strip().casefold() not in {
        "false",
        "0",
        "no",
    }
    skill = Skill(
        id=skill_id,
        name=name,
        description=description,
        instructions=body,
        origin=origin,
        enabled=enabled,
    )
    if not skill.name:
        logger.warning("skill %s has no usable name — skipped", file_path)
        return None
    return skill
