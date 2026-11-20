"""WER scorer tests (§19.3) — known-answer math over normalized forms."""

from __future__ import annotations

import pytest

from nexus.speech.wer import accuracy, character_error_rate, levenshtein, tokenize, word_error_rate


class TestTokenizer:
    def test_normalizes_before_counting(self) -> None:
        assert tokenize("Open the Browser.") == ["open", "the", "browser"]
        assert tokenize("مُتَّصِـفْح") == ["متصفح"]


class TestLevenshtein:
    def test_known_distances(self) -> None:
        assert levenshtein([], []) == 0
        assert levenshtein(["a"], []) == 1
        assert levenshtein(["a", "b"], ["a", "b"]) == 0
        assert levenshtein(["a", "b", "c"], ["a", "x", "c"]) == 1
        assert levenshtein(["a", "b"], ["b", "a"]) == 2


class TestWER:
    def test_identical_is_zero(self) -> None:
        assert word_error_rate("open the browser", "open the browser") == 0.0

    def test_case_and_punctuation_do_not_count(self) -> None:
        assert word_error_rate("Open the Browser.", "open the browser") == 0.0

    def test_arabic_normalization_applies(self) -> None:
        assert word_error_rate("مُتَّصِفْح", "متصفــح") == 0.0

    def test_substitution_counts(self) -> None:
        assert word_error_rate("a b c", "a x c") == pytest.approx(1 / 3)

    def test_deletion_and_insertion(self) -> None:
        assert word_error_rate("a b c", "a c") == pytest.approx(1 / 3)
        assert word_error_rate("a b", "a x b") == pytest.approx(1 / 2)

    def test_full_miss_exceeds_one(self) -> None:
        # two reference tokens, three wrong ones: 2 subs + 1 insertion over 2
        assert word_error_rate("a b", "x y z") == pytest.approx(1.5)

    def test_empty_reference_law(self) -> None:
        assert word_error_rate("", "") == 0.0
        assert word_error_rate("", "x y") == 2.0

    def test_accuracy_floors_at_zero(self) -> None:
        assert accuracy("a b", "x y z") == 0.0
        assert accuracy("a b", "a b") == 1.0


class TestCER:
    def test_character_level(self) -> None:
        assert character_error_rate("اختبار", "اختبار") == 0.0
        # one deletion (the second alef) over six characters
        assert character_error_rate("اختبار", "اختبر") == pytest.approx(1 / 6)

    def test_cer_ignores_spaces(self) -> None:
        assert character_error_rate("a b", "ab") == 0.0
