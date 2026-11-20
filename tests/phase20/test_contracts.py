"""§20.1 contract tests — the four nouns, verbatim, with their laws."""

from __future__ import annotations

import dataclasses
from typing import get_type_hints

import pytest

from nexus.verification import (
    REPAIR_STAGES,
    VERIFICATION_DOMAINS,
    Criterion,
    CriterionError,
    CriterionSkipped,
    Evidence,
    Result,
    ResultStatus,
    VerificationEngine,
    VerificationError,
    Verifier,
    make_verifiers,
)


# --------------------------------------------------------------- vocabulary


def test_domains_verbatim() -> None:
    """§20.2 — the nine domains, verbatim and in the plan's order."""
    assert VERIFICATION_DOMAINS == (
        "software",
        "windows",
        "browser",
        "documents",
        "research",
        "git",
        "memory",
        "models",
        "system",
    )


def test_repair_stages_verbatim() -> None:
    """§20.4 — the five stages, verbatim and ordered."""
    assert REPAIR_STAGES == ("fail", "diagnose", "fix", "retest", "verify")


def test_evidence_fields_verbatim() -> None:
    """§20.3 — the five evidence fields, verbatim, in order."""
    names = [f.name for f in dataclasses.fields(Evidence)]
    assert names == ["method", "output", "timestamp", "artifact", "result"]


def test_verifier_is_abstract_contract() -> None:
    """§20.1 — Verifier is a real ABC; the engine only takes verifiers."""
    assert Verifier.__abstractmethods__ >= {"criteria", "verify"}
    verifiers = make_verifiers()
    assert len(verifiers) == 9
    assert [v.domain for v in verifiers] == list(VERIFICATION_DOMAINS)


# ------------------------------------------------------------------ evidence


def test_evidence_requires_method() -> None:
    with pytest.raises(VerificationError):
        Evidence(method="", output="something")


def test_evidence_defaults_are_honest() -> None:
    ev = Evidence(method="probe", output="observed 3 things")
    assert ev.timestamp, "the timestamp must be filled automatically"
    assert ev.artifact == ""  # empty until an EvidenceStore records it
    assert ev.result is ResultStatus.PASS
    assert ev.as_dict() == {
        "method": "probe",
        "output": "observed 3 things",
        "timestamp": ev.timestamp,
        "artifact": "",
        "result": "PASS",
    }


def test_evidence_is_frozen() -> None:
    ev = Evidence(method="probe", output="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.method = "other"  # type: ignore[misc]


# ----------------------------------------------------------------- criterion


def test_criterion_domain_is_validated() -> None:
    with pytest.raises(CriterionError):
        Criterion(id="c", domain="physics", description="not one of the nine")
    with pytest.raises(CriterionError):
        Criterion(id="", domain="software", description="no id")
    with pytest.raises(CriterionError):
        Criterion(id="c", domain="software", description="")


def test_criterion_is_frozen_but_callable() -> None:
    def probe() -> str:
        return "ok"

    crit = Criterion(id="c1", domain="system", description="d", check=probe)
    assert crit.as_dict()["check"] == "callable"
    with pytest.raises(dataclasses.FrozenInstanceError):
        crit.id = "c2"  # type: ignore[misc]


# -------------------------------------------------------------------- result


def test_result_laws() -> None:
    ev = Evidence(method="m", output="o")
    result = Result(criterion_id="c", status=ResultStatus.PASS, evidence=(ev,))
    assert result.passed
    assert result.as_dict()["evidence"][0]["method"] == "m"
    with pytest.raises(VerificationError):
        Result(criterion_id="", status=ResultStatus.PASS)
    with pytest.raises(VerificationError):
        Result(criterion_id="c", status="PASS")  # type: ignore[arg-type]


def test_result_status_vocabulary() -> None:
    assert {s.value for s in ResultStatus} == {"PASS", "FAIL", "ERROR", "SKIP"}


def test_criterion_skipped_is_honest_refusal() -> None:
    """SKIP travels as its own exception — never a silent PASS."""
    assert issubclass(CriterionSkipped, RuntimeError)


# --------------------------------------------------------------------- graph


def test_engine_rejects_bogus_verifier_domain() -> None:
    class Rogue(Verifier):
        id = "rogue"
        domain = "physics"

        def criteria(self) -> tuple:  # type: ignore[override]
            return ()

        def verify(self, criterion):  # type: ignore[override]
            raise AssertionError("never")

    with pytest.raises(VerificationError):
        VerificationEngine(verifiers=(Rogue(),))


def test_engine_rejects_duplicate_domain() -> None:
    left, _ = make_verifiers()[:2]
    right = type(left)()  # a second verifier claiming the same domain
    with pytest.raises(VerificationError):
        VerificationEngine(verifiers=(left, right))


def test_type_hints_carry_the_vocabulary() -> None:
    hints = get_type_hints(Verifier.verify)
    assert hints["return"] is Result
