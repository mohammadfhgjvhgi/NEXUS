"""Intent routing (New Plan §19.4) — the *Intent* stage.

Bilingual rule routing over *normalized* text (the §19.4
Normalization stage feeds it): six NEXUS intents keyed on Arabic and
English trigger words, a deterministic winner law («first keyword in
the normalized utterance wins», ties break by rule order), an
honest ``unknown`` below threshold — never a forced guess.

The *Task* stage maps the winning intent through
``INTENT_TO_TASK_KIND`` (§19.1 contracts) into a real NEXUS task kind.

النية — ست نوايا بالعربية والإنجليزية، فائز محسوم، ومجهول صادق.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .textnorm import normalize_text

#: the intent vocabulary — NEXUS commands a voice can trigger
INTENT_OPEN_APP = "open_app"
INTENT_RUN_COMMAND = "run_command"
INTENT_SEARCH_WEB = "search_web"
INTENT_CREATE_NOTE = "create_note"
INTENT_SYSTEM_STATUS = "system_status"
INTENT_STOP = "stop"
INTENT_UNKNOWN = "unknown"

INTENTS: tuple[str, ...] = (
    INTENT_OPEN_APP,
    INTENT_RUN_COMMAND,
    INTENT_SEARCH_WEB,
    INTENT_CREATE_NOTE,
    INTENT_SYSTEM_STATUS,
    INTENT_STOP,
    INTENT_UNKNOWN,
)


@dataclass(frozen=True, slots=True)
class IntentRule:
    """One intent's triggers — normalized forms, one weight each."""

    intent: str
    keywords: tuple[str, ...]
    weight: float = 1.0


#: the default bilingual rule table (normalized forms — «شغّل» lands as
#: «شغل», «حالة» as «حاله» through the §19.4 normalizer)
DEFAULT_RULES: tuple[IntentRule, ...] = (
    IntentRule(
        INTENT_OPEN_APP,
        ("افتح", "فتح", "open", "launch", "show"),
    ),
    IntentRule(
        INTENT_RUN_COMMAND,
        ("شغل", "نفذ", "run", "execute", "start"),
    ),
    IntentRule(
        INTENT_SEARCH_WEB,
        ("ابحث", "دور", "search", "find"),
    ),
    IntentRule(
        INTENT_CREATE_NOTE,
        ("دون", "اكتب", "ملاحظه", "note", "write"),
        weight=0.9,
    ),
    IntentRule(
        INTENT_SYSTEM_STATUS,
        ("حاله", "status", "health"),
    ),
    IntentRule(
        INTENT_STOP,
        ("قف", "اوقف", "توقف", "stop", "cancel", "quit"),
    ),
)


@dataclass(frozen=True, slots=True)
class IntentResult:
    """The router's verdict — intent, confidence, and what's left over."""

    intent: str
    confidence: float
    argument: str = ""
    matched: tuple[str, ...] = field(default_factory=tuple)
    normalized_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 4),
            "argument": self.argument,
            "matched": list(self.matched),
            "normalized_text": self.normalized_text,
        }


class IntentRouter:
    """Normalized utterance → :class:`IntentResult` — deterministic."""

    #: below this a hit does not win — the honest «unknown»
    CONFIDENCE_FLOOR = 0.5

    def __init__(self, rules: tuple[IntentRule, ...] | None = None) -> None:
        self._rules = rules if rules is not None else DEFAULT_RULES

    def route(self, text: str) -> IntentResult:
        normalized = normalize_text(text)
        tokens = normalized.split()
        best_score, best_rule, best_keyword = 0.0, None, ""
        for rule in self._rules:
            hits = 0
            hit_keyword = ""
            for keyword in rule.keywords:
                if keyword in tokens:
                    hits += 1
                    if not hit_keyword:
                        hit_keyword = keyword
            # cap at two distinct keyword hits — repetition is not intent
            score = min(2, hits) * rule.weight / 2.0
            if score > best_score:
                best_score, best_rule, best_keyword = score, rule, hit_keyword
        if best_rule is None or best_score < self.CONFIDENCE_FLOOR:
            return IntentResult(
                intent=INTENT_UNKNOWN,
                confidence=round(best_score, 4),
                argument=normalized,
                normalized_text=normalized,
            )
        # the argument is whatever follows the winning keyword
        if best_keyword in tokens:
            pos = tokens.index(best_keyword)
            argument = " ".join(tokens[pos + 1 :])
        else:  # pragma: no cover — keyword came from tokens, cannot miss
            argument = ""
        return IntentResult(
            intent=best_rule.intent,
            confidence=round(best_score, 4),
            argument=argument,
            matched=(best_keyword,),
            normalized_text=normalized,
        )
