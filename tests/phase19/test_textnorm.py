"""Normalization tests (§19.4) — one law per script, mixed included."""

from __future__ import annotations

from nexus.speech.textnorm import (
    detect_script,
    normalize_arabic_token,
    normalize_text,
    script_inferred_language,
    strip_diacritics,
)


class TestArabic:
    def test_diacritics_and_tatweel_strip(self) -> None:
        assert normalize_arabic_token("مُتَّصِـفْح") == "متصفح"

    def test_alef_forms_unify_in_context(self) -> None:
        assert normalize_arabic_token("أفتاح") == normalize_arabic_token("افتاح")
        assert normalize_arabic_token("إرسال") == normalize_arabic_token("ارسال")

    def test_hamza_alef_family(self) -> None:
        assert normalize_arabic_token("أ") == normalize_arabic_token("ا")
        assert normalize_arabic_token("إ") == normalize_arabic_token("ا")
        assert normalize_arabic_token("آ") == normalize_arabic_token("ا")

    def test_taa_marbuta_and_alef_maqsura(self) -> None:
        assert normalize_arabic_token("مكتبة") == "مكتبه"
        assert normalize_arabic_token("على") == "علي"

    def test_arabic_indic_digits(self) -> None:
        assert normalize_arabic_token("٨٠٨٠") == "8080"
        assert normalize_arabic_token("۲۵") == "25"

    def test_diacritics_only_helper(self) -> None:
        assert strip_diacritics("عَلَيْهِ") == "عليه"


class TestMixed:
    def test_mixed_line_normalizes_per_token(self) -> None:
        out = normalize_text("افتح الـ Terminal وشغل npm test.")
        assert out == "افتح ال terminal وشغل npm test"

    def test_punctuation_stripped_at_edges(self) -> None:
        assert normalize_text("\"Run\", the tests…") == "run the tests"

    def test_whitespace_collapses(self) -> None:
        assert normalize_text("  open   the  ") == "open the"


class TestScriptDetection:
    def test_scripts(self) -> None:
        assert detect_script("افتح المتصفح") == "arabic"
        assert detect_script("open the browser") == "latin"
        assert detect_script("افتح terminal وشغل npm") == "mixed"
        assert detect_script("١٢٣") == "other"

    def test_language_inference_codes(self) -> None:
        assert script_inferred_language("افتح المتصفح") == "ar"
        assert script_inferred_language("Open it") == "en"
        assert script_inferred_language("افتح terminal") == "mixed"
        assert script_inferred_language("...") == "unknown"
