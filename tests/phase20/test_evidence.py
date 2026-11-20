"""§20.3 evidence tests — five fields, sealed artifacts, honest refusals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.verification import Evidence, EvidenceStore, ResultStatus, VerificationError


@pytest.fixture()
def store(tmp_path: Path) -> EvidenceStore:
    return EvidenceStore(tmp_path / "proofs")


def test_record_sets_artifact_and_seals_sha(store: EvidenceStore) -> None:
    ev = store.record(Evidence(method="probe:demo", output="observed 1 thing"))
    assert ev.artifact.startswith("evidence/ev-")
    envelope = store.read_back(ev.artifact)
    assert envelope["sha256"], "the artifact carries its integrity digest"
    fields = envelope["evidence"]
    assert sorted(fields.keys()) == sorted(
        ["method", "output", "timestamp", "artifact", "result"]
    )
    assert fields["method"] == "probe:demo"
    assert fields["result"] == "PASS"


def test_read_back_detects_tampering(store: EvidenceStore) -> None:
    ev = store.record(Evidence(method="probe:demo", output="original output"))
    path = store.root / ev.artifact
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["evidence"]["output"] = "tampered output"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(VerificationError, match="integrity"):
        store.read_back(ev.artifact)


def test_read_back_rejects_missing_and_foreign(store: EvidenceStore, tmp_path: Path) -> None:
    with pytest.raises(VerificationError, match="does not exist"):
        store.read_back("evidence/ev-nowhere.json")
    with pytest.raises(VerificationError, match="escapes"):
        store.read_back("../outside.json")


def test_record_refuses_unlabelled_observation(store: EvidenceStore) -> None:
    with pytest.raises(VerificationError, match="no output"):
        store.record(Evidence(method="probe:empty", output=""))


def test_record_is_idempotent_on_identical_evidence(store: EvidenceStore) -> None:
    first = store.record(
        Evidence(method="probe:same", output="same observation", timestamp="2026-01-01T00:00:00+00:00")
    )
    second = store.record(
        Evidence(method="probe:same", output="same observation", timestamp="2026-01-01T00:00:00+00:00")
    )
    assert first.artifact == second.artifact
    assert store.count() == 1


def test_every_status_can_be_recorded(store: EvidenceStore) -> None:
    for status in ResultStatus:
        ev = store.record(Evidence(method=f"probe:{status.value}", output="o", result=status))
        envelope = store.read_back(ev.artifact)
        assert envelope["evidence"]["result"] == status.value


def test_persist_report_and_count(store: EvidenceStore) -> None:
    store.record(Evidence(method="probe:a", output="a"))
    store.record(Evidence(method="probe:b", output="b"))
    name = store.persist_report({"overall": "PASS", "total": 2}, name="report.json")
    assert name == "report.json"
    doc = json.loads((store.root / "report.json").read_text(encoding="utf-8"))
    assert doc["report"]["overall"] == "PASS"
    assert doc["sha256"]
    assert store.count() == 2


def test_report_name_cannot_escape(store: EvidenceStore) -> None:
    with pytest.raises(VerificationError, match="escapes"):
        store.persist_report({}, name="../evil.json")
