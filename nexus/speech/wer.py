"""WER scoring (New Plan §19.3) — the benchmark's measuring stick.

Pure-stdlib Levenshtein scoring over *normalized* tokens (the §19.4
Normalization stage feeds it), so «Run the full system check now.»
scores identical to «run the full system check now».  Arabic is scored
through the same normalization (diacritics stripped, alef forms
unified), with a character-level variant (CER) for the short-utterance
cases where token counts are small.

الدرج — WER/CER بعد التطبيع، صفر تبعيات، رياضيات معروفة.
"""

from __future__ import annotations

from .textnorm import normalize_text


def tokenize(text: str) -> list[str]:
    """Normalized token list — the scorer's unit."""
    return normalize_text(text).split()


def levenshtein(a: list[str], b: list[str]) -> int:
    """Token-level edit distance (O(len·len) DP, fine for utterances)."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ta in enumerate(a, start=1):
        cur = [i]
        for j, tb in enumerate(b, start=1):
            cur.append(
                min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ta != tb))
            )
        prev = cur
    return prev[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER over normalized tokens — 0.0 identical, may exceed 1.0.

    Empty reference is not a division by zero: an empty hypothesis
    scores 0.0, a non-empty one scores its full insertion count.
    """
    ref = tokenize(reference)
    hyp = tokenize(hypothesis)
    if not ref:
        return 0.0 if not hyp else float(len(hyp))
    return levenshtein(ref, hyp) / float(len(ref))


def accuracy(reference: str, hypothesis: str) -> float:
    """``max(0, 1 - WER)`` — a floor at zero, never negative."""
    return max(0.0, 1.0 - word_error_rate(reference, hypothesis))


def character_error_rate(reference: str, hypothesis: str) -> float:
    """CER over normalized *characters* (spaces excluded) — Arabic's
    fine-grained companion for short utterances."""
    ref = [c for c in normalize_text(reference) if c != " "]
    hyp = [c for c in normalize_text(hypothesis) if c != " "]
    if not ref:
        return 0.0 if not hyp else float(len(hyp))
    return levenshtein(ref, hyp) / float(len(ref))
