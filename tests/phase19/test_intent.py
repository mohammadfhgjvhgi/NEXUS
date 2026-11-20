"""Intent router tests (§19.4) — bilingual triggers, honest unknown."""

from __future__ import annotations

import pytest

from nexus.speech.intent import (
    INTENT_CREATE_NOTE,
    INTENT_OPEN_APP,
    INTENT_RUN_COMMAND,
    INTENT_SEARCH_WEB,
    INTENT_STOP,
    INTENT_SYSTEM_STATUS,
    INTENT_UNKNOWN,
    IntentRouter,
)


@pytest.fixture()
def router() -> IntentRouter:
    return IntentRouter()


class TestArabicIntents:
    def test_open_app(self, router: IntentRouter) -> None:
        verdict = router.route("افتح المتصفح")
        assert verdict.intent == INTENT_OPEN_APP
        assert verdict.argument == "المتصفح"

    def test_run_command_with_diacritics(self, router: IntentRouter) -> None:
        # «شغّل» normalizes to «شغل» — the trigger matches anyway
        verdict = router.route("شغّل خدمة قاعدة البيانات")
        assert verdict.intent == INTENT_RUN_COMMAND

    def test_search(self, router: IntentRouter) -> None:
        assert router.route("ابحث عن اختبار الوحدة").intent == INTENT_SEARCH_WEB

    def test_status(self, router: IntentRouter) -> None:
        # «حالة» → «حاله» through the normalizer
        assert router.route("حالة النظام").intent == INTENT_SYSTEM_STATUS

    def test_stop(self, router: IntentRouter) -> None:
        assert router.route("أوقف المهمة").intent == INTENT_STOP


class TestEnglishIntents:
    def test_open(self, router: IntentRouter) -> None:
        assert router.route("Open the browser").intent == INTENT_OPEN_APP

    def test_run(self, router: IntentRouter) -> None:
        assert router.route("Run the full check now").intent == INTENT_RUN_COMMAND

    def test_find(self, router: IntentRouter) -> None:
        assert router.route("find the config file").intent == INTENT_SEARCH_WEB

    def test_cancel(self, router: IntentRouter) -> None:
        assert router.route("cancel that").intent == INTENT_STOP


class TestMixedAndUnknown:
    def test_mixed_utterance(self, router: IntentRouter) -> None:
        verdict = router.route("افتح الـ terminal وشغل npm test")
        assert verdict.intent == INTENT_OPEN_APP  # first keyword wins
        assert "terminal" in verdict.argument

    def test_unknown_is_honest(self, router: IntentRouter) -> None:
        verdict = router.route("السماء الزرقاء اليوم جميلة")
        assert verdict.intent == INTENT_UNKNOWN
        assert verdict.confidence == 0.0
        assert verdict.argument  # the line is preserved, not dropped

    def test_confidence_is_bounded(self, router: IntentRouter) -> None:
        for line in ("افتح المتصفح", "run it", "cancel", "مجهول تماما"):
            verdict = router.route(line)
            assert 0.0 <= verdict.confidence <= 1.0

    def test_first_keyword_wins_the_argument(self, router: IntentRouter) -> None:
        verdict = router.route("open the terminal and run the tests")
        assert verdict.intent == INTENT_OPEN_APP
        assert verdict.argument.startswith("the terminal")


class TestNotes:
    def test_note_weight_below_one_still_wins_alone(self, router: IntentRouter) -> None:
        verdict = router.route("اكتب ملاحظة سريعة")
        assert verdict.intent == INTENT_CREATE_NOTE
        # 0.9 * 2 hits capped / 2 → 0.9 ≥ floor
        assert verdict.confidence == pytest.approx(0.9)
