"""Text normalization (New Plan §19.4) — the *Normalization* stage.

One normalizer for the three §19.3 language shapes — Arabic, English
and mixed Arabic-English — because the *Intent* stage downstream keys
on normalized forms:

* Arabic: diacritics (tashkeel) and tatweel stripped, alef forms
  unified (أ إ آ ٱ → ا), ى → ي, ة → ه, ؤ → و, ئ → ي, Arabic-Indic
  digits (٠-٩ and the Persian ۰-۹) mapped to Western digits.
* English: lowercased.
* Both: edge punctuation stripped per token, whitespace collapsed.

Mixed utterances are normalized per token — a token's script decides
its rules, so ``افتح الـ terminal وشغل npm test`` survives as one
normalized line.  The same mapping feeds the WER scorer (§19.3) so the
benchmark compares normalized forms, never raw casing or diacritics.

التطبيع — الخطوة الثالثة في سير الصوت، واحدة للعربية والإنجليزية والمختلط.
"""

from __future__ import annotations

import re
import string
import unicodedata

_ARABIC_MARKS = re.compile(r"[\u064B-\u0652\u0670\u0640]")  # tashkeel + dagger alif + tatweel

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_ALEF_MAP = {
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ى": "ي",
    "ئ": "ي",
    "ؤ": "و",
    "ة": "ه",
}

#: Edge punctuation — ASCII plus the Arabic separators ، ؛ ؟ « » …
_PUNCT = set(string.punctuation) | set("،؛؟«»…")

_ARABIC_ANY_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")  # letters + marks + digits
# letters only — digits are not a script on their own
_ARABIC_LETTER_RE = re.compile(r"[\u0621-\u064A\u0671-\u06D3]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def normalize_arabic_token(token: str) -> str:
    """One Arabic token → its normalized form (letters and digits)."""
    out = _ARABIC_MARKS.sub("", token)
    out = out.translate(_ARABIC_DIGITS)
    return "".join(_ALEF_MAP.get(ch, ch) for ch in out)


def detect_script(text: str) -> str:
    """``arabic`` | ``latin`` | ``mixed`` | ``other`` — honest ranges.

    Digits (even Arabic-Indic ones) are not a script on their own:
    ``١٢٣`` alone is ``other``; letters decide.
    """
    arabic = len(_ARABIC_LETTER_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if arabic and latin:
        return "mixed"
    if arabic:
        return "arabic"
    if latin:
        return "latin"
    return "other"


def normalize_token(token: str) -> str:
    """One token — script decides: Arabic laws, Latin lowercasing."""
    core = token.strip("".join(_PUNCT))
    if not core:
        return ""
    if _ARABIC_ANY_RE.search(core):
        core = normalize_arabic_token(core)
    return core.lower()


def normalize_text(text: str) -> str:
    """A whole utterance → normalized, whitespace-collapsed text."""
    tokens = (normalize_token(t) for t in text.split())
    return " ".join(t for t in tokens if t)


def script_inferred_language(text: str) -> str:
    """Transcript unicode ranges → a language code (SAPI's honest path).

    ``ar`` / ``en`` / ``mixed`` / ``unknown`` — the method is reported
    alongside the code in :class:`~nexus.speech.contracts.LanguageDetection`
    so no consumer mistakes inference for an engine's native report.
    """
    script = detect_script(text)
    return {
        "arabic": "ar",
        "latin": "en",
        "mixed": "mixed",
        "other": "unknown",
    }[script]


def strip_diacritics(text: str) -> str:
    """Tashkeel/tatweel removal only — exposed for the WER tests.

    (NFKD decomposition is deliberately *not* used on Arabic: it splits
    lam-alef ligatures and breaks roundtrip comparisons.)
    """
    return _ARABIC_MARKS.sub("", unicodedata.normalize("NFC", text))
