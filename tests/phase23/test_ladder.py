"""§23.3 Recovery Ladder — five rungs, walked, observable, never silent."""

from __future__ import annotations

from nexus.health import (
    RECOVERY_LADDER,
    Diagnosis,
    LadderOutcome,
    RecoveryLadder,
    RecoveryResolution,
    StallFinding,
    StallSignal,
)


def finding(signal: StallSignal = StallSignal.SAME_ACTION) -> StallFinding:
    return StallFinding(signal=signal, repeats=3, detail="loop", component=None)


def test_retry_resolves_at_the_third_rung() -> None:
    ladder = RecoveryLadder(retry=lambda f: True)
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.RESOLVED
    assert outcome.rungs == ("detect", "diagnose", "retry")
    assert outcome.stopped_at == "retry"
    assert outcome.diagnosis is not None
    assert outcome.diagnosis.signal is StallSignal.SAME_ACTION


def test_retry_fails_alternate_method_resolves() -> None:
    ladder = RecoveryLadder(retry=lambda f: False, alternate=lambda f: True)
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.RESOLVED
    assert outcome.rungs == ("detect", "diagnose", "retry", "alternate_method")
    assert outcome.stopped_at == "alternate_method"
    assert "retry: attempted, did not resolve" in outcome.detail
    assert "alternate_method: resolved" in outcome.detail


def test_both_rungs_fail_replan_is_the_last_word() -> None:
    ladder = RecoveryLadder(retry=lambda f: False, alternate=lambda f: False)
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.REPLAN_NEEDED
    assert outcome.rungs == RECOVERY_LADDER
    assert outcome.stopped_at == "replan"


def test_refuted_finding_ends_honestly_at_detect() -> None:
    ladder = RecoveryLadder(confirm=lambda f: False, retry=lambda f: True)
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.NOT_CONFIRMED
    assert outcome.rungs == ("detect",)
    assert outcome.stopped_at == "detect"
    assert "did not survive re-observation" in outcome.detail


def test_absent_rungs_climb_honestly() -> None:
    ladder = RecoveryLadder()  # nothing registered — the full honest climb
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.REPLAN_NEEDED
    assert outcome.rungs == RECOVERY_LADDER
    assert "retry: not registered" in outcome.detail
    assert "alternate_method: not registered" in outcome.detail
    assert "no replanner registered" in outcome.detail


def test_a_raising_rung_climbs_never_dies() -> None:
    def boom(f: StallFinding) -> bool:
        raise RuntimeError("device gone")

    ladder = RecoveryLadder(retry=boom, alternate=lambda f: True)
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.RESOLVED
    assert "retry: raised RuntimeError: device gone" in outcome.detail
    assert outcome.rungs == ("detect", "diagnose", "retry", "alternate_method")


def test_pluggable_diagnose_replaces_the_default_table() -> None:
    mine = Diagnosis(signal=StallSignal.SAME_ERROR, cause="driver", confidence=0.8)
    ladder = RecoveryLadder(
        diagnose=lambda f: mine, retry=lambda f: True
    )
    outcome = ladder.handle(finding(StallSignal.SAME_ERROR))
    assert outcome.diagnosis == mine


def test_default_diagnose_table_covers_all_four_signals() -> None:
    from nexus.health.engine import DEFAULT_CAUSES

    for signal in StallSignal:
        ladder = RecoveryLadder()
        outcome = ladder.handle(finding(signal))
        assert outcome.diagnosis is not None
        assert outcome.diagnosis.cause == DEFAULT_CAUSES[signal]
        assert outcome.diagnosis.cause  # never an empty explanation


def test_before_rung_announces_each_mutating_rung() -> None:
    announced: list[str] = []
    ladder = RecoveryLadder(
        retry=lambda f: False,
        alternate=lambda f: True,
        before_rung=lambda rung, f: announced.append(rung),
    )
    ladder.handle(finding())
    assert announced == ["retry", "alternate_method"]


def test_a_failing_announcement_refuses_the_rung() -> None:
    """The §22 law: no checkpoint, no risky change — the ladder climbs."""

    def no_checkpoint(rung: str, f: StallFinding) -> None:
        raise RuntimeError("§22 store unavailable")

    ladder = RecoveryLadder(
        retry=lambda f: True,  # would "resolve" — but it must never run
        before_rung=no_checkpoint,
    )
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.REPLAN_NEEDED
    assert "retry" not in outcome.rungs  # the rung never fired
    assert "REFUSED" in outcome.detail
    assert outcome.rungs == ("detect", "diagnose", "alternate_method", "replan")


def test_replanner_return_value_is_respected() -> None:
    ladder = RecoveryLadder(replan=lambda f: RecoveryResolution.REPLAN_NEEDED)
    outcome = ladder.handle(finding())
    assert outcome.resolution is RecoveryResolution.REPLAN_NEEDED

    def hands_off(f: StallFinding) -> None:
        return None

    outcome2 = RecoveryLadder(replan=hands_off).handle(finding())
    assert outcome2.resolution is RecoveryResolution.REPLAN_NEEDED


def test_outcome_stages_always_the_verbatim_prefix() -> None:
    ladder = RecoveryLadder(retry=lambda f: False, alternate=lambda f: False)
    outcome: LadderOutcome = ladder.handle(finding())
    assert RECOVERY_LADDER[: len(outcome.stages)] == outcome.stages
