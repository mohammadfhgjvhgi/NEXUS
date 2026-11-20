"""§23.2 Stall Detection — the four loop shapes, named verbatim.

The builder law: every field the test does not pin *varies* — a loop
must be planted deliberately, never inherited from defaults.
"""

from __future__ import annotations

import pytest

from nexus.health import Observation, StallDetector, StallSignal
from nexus.health.heartbeat import HealthError

R = 3  # the repeat threshold used throughout
_TICK = iter(range(1_000_000))


def obs(
    action: str | None = None,
    error: str = "",
    state: str | None = None,
    progress: str | None = None,
) -> Observation:
    """One observation — unpinned action/state/progress vary per call."""
    tick = next(_TICK)
    return Observation(
        action=action if action is not None else f"act-{tick}",
        error=error,
        state=state if state is not None else f"state-{tick}",
        progress=progress if progress is not None else f"prog-{tick}",
    )


def test_same_action_fires_at_the_threshold() -> None:
    d = StallDetector(repeat_threshold=R)
    assert d.observe(obs(action="click")) == ()
    assert d.observe(obs(action="click")) == ()
    (finding,) = d.observe(obs(action="click"))  # state/progress vary — isolated
    assert finding.signal is StallSignal.SAME_ACTION
    assert finding.repeats == R
    assert "click" in finding.detail


def test_same_error_fires_and_names_the_signature() -> None:
    d = StallDetector(repeat_threshold=R)
    for _ in range(R - 1):
        assert d.observe(obs(error="WinError32:file locked")) == ()
    (finding,) = d.observe(obs(error="WinError32:file locked"))
    assert finding.signal is StallSignal.SAME_ERROR
    assert "WinError32" in finding.detail


def test_same_state_fires_on_a_frozen_hash() -> None:
    d = StallDetector(repeat_threshold=R)
    for _i in range(R - 1):  # action/progress vary — only the hash is pinned
        assert d.observe(obs(state="dead-hash")) == ()
    (finding,) = d.observe(obs(state="dead-hash"))
    assert finding.signal is StallSignal.SAME_STATE


def test_no_progress_fires_when_the_window_never_moves() -> None:
    d = StallDetector(repeat_threshold=R, progress_window=5)
    for _ in range(4):  # below the window — nothing yet
        assert d.observe(obs(progress="p1")) == ()
    (finding,) = d.observe(obs(progress="p1"))
    assert finding.signal is StallSignal.NO_PROGRESS
    assert finding.repeats == 5


def test_no_progress_falls_back_to_state_when_unmarked() -> None:
    d = StallDetector(repeat_threshold=5, progress_window=4)
    for _ in range(3):  # no progress marker at all — the state is the only voice
        assert d.observe(obs(state="frozen", progress="")) == ()
    (finding,) = d.observe(obs(state="frozen", progress=""))
    assert finding.signal is StallSignal.NO_PROGRESS


def test_progress_moving_means_no_finding() -> None:
    d = StallDetector(repeat_threshold=R, progress_window=5)
    for i in range(8):
        assert d.observe(obs(progress=f"step-{i}", state=f"hash-{i}")) == ()


def test_healthy_flow_fires_nothing() -> None:
    d = StallDetector(repeat_threshold=R, progress_window=5)
    for _ in range(16):
        assert d.observe(obs()) == ()  # everything varies — a live worker


def test_empty_fields_are_never_judged() -> None:
    d = StallDetector(repeat_threshold=2)
    assert d.observe(Observation(), Observation(), Observation()) == ()


def test_fires_once_per_evidence_no_spam() -> None:
    d = StallDetector(repeat_threshold=R)
    for _ in range(R):
        d.observe(obs(action="click"))  # the 3rd click fires
    assert d.observe(obs(action="click")) == ()  # same evidence — no re-fire
    assert d.observe(obs(action="click")) == ()
    d.observe(obs(action="type"))  # the run breaks — the signal re-arms
    d.observe(obs(action="type"))
    (refired,) = d.observe(obs(action="type"))  # a new run of three
    assert refired.signal is StallSignal.SAME_ACTION


def test_reset_rearms_after_a_recovery() -> None:
    d = StallDetector(repeat_threshold=R)
    for _ in range(R):
        d.observe(obs(action="click"))
    d.reset()
    assert d.depth == 0
    assert d.observe(obs(action="click")) == ()
    assert d.observe(obs(action="click")) == ()
    (finding,) = d.observe(obs(action="click"))
    assert finding.signal is StallSignal.SAME_ACTION


def test_a_single_distinct_step_breaks_the_run() -> None:
    d = StallDetector(repeat_threshold=R)
    d.observe(obs(action="click"))
    d.observe(obs(action="click"))
    d.observe(obs(action="type"))  # breaks the run
    assert d.observe(obs(action="click")) == ()
    assert d.observe(obs(action="click")) == ()


def test_thresholds_are_validated() -> None:
    with pytest.raises(HealthError):
        StallDetector(repeat_threshold=1)
    with pytest.raises(HealthError):
        StallDetector(progress_window=1)


def test_all_four_signals_fire_together_on_a_fully_frozen_loop() -> None:
    d = StallDetector(repeat_threshold=R, progress_window=3)
    frozen = dict(action="click", error="E:timeout", state="s1", progress="p1")
    assert d.observe(obs(**frozen)) == ()
    assert d.observe(obs(**frozen)) == ()
    findings = d.observe(obs(**frozen))  # threshold AND window reached together
    assert {f.signal for f in findings} == set(StallSignal)
