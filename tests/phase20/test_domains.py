"""§20.2 domain tests — nine verifiers, honest statuses, real probes."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

import pytest

from nexus.verification import (
    VERIFICATION_DOMAINS,
    Criterion,
    CriterionSkipped,
    Evidence,
    Result,
    ResultStatus,
    VerificationEngine,
    make_verifiers,
)
from nexus.verification.domains import BaseVerifier


def _status(result: Result) -> ResultStatus:
    return result.status


def test_all_nine_verifiers_declared() -> None:
    verifiers = make_verifiers()
    assert {v.domain for v in verifiers} == set(VERIFICATION_DOMAINS)
    for verifier in verifiers:
        criteria = verifier.criteria()
        assert criteria, f"{verifier.id} declares no criteria"
        for criterion in criteria:
            assert criterion.domain == verifier.domain
            assert criterion.check is not None


def test_every_result_carries_five_field_evidence() -> None:
    """The §20.3 law, enforced over every criterion of every domain."""
    engine = VerificationEngine()
    report = engine.run()
    assert report.total == sum(len(v.criteria()) for v in engine.verifiers)
    for result in report.results:
        assert result.evidence, f"{result.criterion_id} has no evidence — an unproven claim"
        for ev in result.evidence:
            assert ev.method
            assert ev.output
            assert ev.timestamp  # ISO UTC
            assert isinstance(ev.result, ResultStatus)


def test_software_domain_fully_passes() -> None:
    engine = VerificationEngine()
    report = engine.run(domains=("software",))
    assert report.overall == "PASS"
    assert report.tallies["software"].skipped == 0


def test_memory_domain_roundtrip_passes() -> None:
    engine = VerificationEngine()
    report = engine.run(domains=("memory",))
    assert report.overall == "PASS", [
        (r.criterion_id, r.evidence[0].output) for r in report.results if not r.passed
    ]


def test_system_domain_fully_passes() -> None:
    engine = VerificationEngine()
    report = engine.run(domains=("system",))
    assert report.overall == "PASS"
    assert report.tallies["system"].skipped == 0


def test_git_domain_passes_inside_a_repo() -> None:
    """In a real repo the HEAD is read; on a deployed tree it honestly skips."""
    engine = VerificationEngine()
    report = engine.run(domains=("git",))
    assert report.failed == 0 and report.errored == 0, [
        (r.criterion_id, r.evidence[0].output) for r in report.results if not r.passed
    ]
    probe = next(r for r in report.results if r.criterion_id == "git-repo-root-probe")
    if probe.status is ResultStatus.SKIP:
        # a deployed (non-repo) tree — the probe's honest refusal
        assert "no .git above the package" in probe.evidence[0].output
    else:
        assert probe.passed
        assert "HEAD" in probe.evidence[0].output


def test_windows_domain_is_honest_off_windows(tmp_path: Path) -> None:
    """On POSIX the Windows facts SKIP honestly; on Windows they're judged."""
    engine = VerificationEngine()
    report = engine.run(domains=("windows",))
    windows_tally = report.tallies["windows"]
    assert windows_tally.failed == 0 and windows_tally.errored == 0
    if platform.system() != "Windows":
        assert windows_tally.skipped >= 1, "off-Windows the platform probe must SKIP"
        platform_result = next(
            r for r in report.results if r.criterion_id == "windows-platform-probe"
        )
        assert _status(platform_result) is ResultStatus.SKIP
        assert "judged on the real box" in platform_result.evidence[0].output
    else:
        assert windows_tally.passed >= 1


def test_models_and_documents_probes_stay_honest() -> None:
    engine = VerificationEngine()
    report = engine.run(domains=("models", "documents"))
    assert report.failed == 0 and report.errored == 0
    # each SKIP carries its honest reason in the evidence output
    for result in report.results:
        if _status(result) is ResultStatus.SKIP:
            assert result.evidence[0].output.startswith("skipped:")


def test_browser_vocabulary_passes_without_playwright() -> None:
    """The vocabulary criterion holds everywhere; only the engine probe skips."""
    engine = VerificationEngine()
    report = engine.run(domains=("browser",))
    vocab = next(r for r in report.results if r.criterion_id == "browser-package-vocabulary")
    assert vocab.passed
    assert report.tallies["browser"].failed == 0


# --------------------------------------------------- the base engine's laws


class _Probe(BaseVerifier):
    """A synthetic verifier exercising the four honest outcomes."""

    id = "probe-verifier"
    domain = "system"

    def criteria(self):  # type: ignore[override]
        def ok() -> str:
            return "all good"

        def fail() -> str:
            raise AssertionError("the claim did not hold")

        def skip() -> str:
            raise CriterionSkipped("cannot judge here")

        def boom() -> str:
            raise ValueError("probe broken")

        return (
            Criterion(id="system-probe-ok", domain="system", description="d", check=ok),
            Criterion(id="system-probe-fail", domain="system", description="d", check=fail),
            Criterion(id="system-probe-skip", domain="system", description="d", check=skip),
            Criterion(id="system-probe-boom", domain="system", description="d", check=boom),
        )


def test_base_verifier_maps_outcomes_honestly(tmp_path: Path) -> None:
    verifier = _Probe()
    statuses = {v.verify(c).status for c, v in [(c, verifier) for c in verifier.criteria()]}
    assert statuses == {
        ResultStatus.PASS,
        ResultStatus.FAIL,
        ResultStatus.SKIP,
        ResultStatus.ERROR,
    }
    fail = verifier.verify(verifier.criteria()[1])
    assert "did not hold" in fail.message
    error = verifier.verify(verifier.criteria()[3])
    assert "ValueError" in error.message


def test_base_verifier_persists_evidence(tmp_path: Path) -> None:
    from nexus.verification import EvidenceStore

    store = EvidenceStore(tmp_path / "proofs")
    verifier = _Probe(store=store)
    result = verifier.verify(verifier.criteria()[0])
    assert result.evidence[0].artifact.startswith("evidence/ev-")
    envelope = store.read_back(result.evidence[0].artifact)
    assert envelope["evidence"]["output"] == "all good"


def test_criterion_without_check_is_rejected(tmp_path: Path) -> None:
    verifier = _Probe()
    naked = Criterion(id="system-naked", domain="system", description="d", check=None)
    with pytest.raises(Exception, match="declares no check"):
        verifier.verify(naked)


def test_output_is_truncated_to_readability() -> None:
    from nexus.verification.domains import _MAX_OUTPUT

    class Loud(BaseVerifier):
        id = "loud"
        domain = "system"

        def criteria(self):  # type: ignore[override]
            def shout() -> str:
                return "x" * 5000

            return (
                Criterion(id="system-shout", domain="system", description="d", check=shout),
            )

    result = Loud().verify(Loud().criteria()[0])
    assert len(result.evidence[0].output) == _MAX_OUTPUT


def test_skip_evidence_records_reason() -> None:
    engine = VerificationEngine()
    if sys.platform == "win32":
        pytest.skip("this test asserts the POSIX-side honest SKIP")
    report = engine.run_domain("windows")
    platform_result = next(r for r in report.results if r.criterion_id == "windows-platform-probe")
    ev = platform_result.evidence[0]
    assert isinstance(ev, Evidence)
    assert ev.result is ResultStatus.SKIP
    assert platform.system() in ev.output
