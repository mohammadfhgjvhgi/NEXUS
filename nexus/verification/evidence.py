"""Evidence persistence (New Plan §20.3).

Every criterion's proof outlives the run: each :class:`Evidence` is
written as a JSON artifact under the store root, self-describing with
its five verbatim fields (``method`` · ``output`` · ``timestamp`` ·
``artifact`` · ``result``) plus a sha256 integrity digest — so a
read-back can prove the artifact was not touched after the fact.

The store never judges and never invents: it persists exactly what the
verifiers observed, and refuses to record evidence that is missing its
method or output (an unlabelled observation is no observation).

برهان §20.3 — كل معيار بحقوله الخمسة، محفوظاً كهوية قابلة للقراءة
الراجعة مع بصمة sha256.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import Evidence, ResultStatus, VerificationError, utc_now_iso

#: The envelope key holding the artifact's own integrity digest.
SHA_KEY = "sha256"


class EvidenceStore:
    """Where proofs land — one JSON artifact per recorded observation."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._evidence_dir = self.root / "evidence"
        self._evidence_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- paths

    def _artifact_path(self, artifact: str) -> Path:
        """Resolve a stored artifact id (relative name) under the root."""
        candidate = (self.root / artifact).resolve()
        root = self.root.resolve()
        if root not in candidate.parents:
            raise VerificationError(f"artifact {artifact!r} escapes the store root")
        return candidate

    # ------------------------------------------------------------ record

    def record(self, evidence: Evidence) -> Evidence:
        """Persist one observation; returns a copy with its artifact set.

        The artifact is a JSON envelope::

            {"sha256": "<digest of the evidence JSON>",
             "evidence": {method, output, timestamp, artifact, result}}

        The digest is computed over the evidence object itself, so the
        read-back can re-verify integrity independently of where the
        file sits on disk.
        """
        if not evidence.output:
            raise VerificationError(
                f"evidence {evidence.method!r} has no output — an "
                "unlabelled observation is no observation"
            )
        payload = evidence.as_dict()
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        name = f"ev-{digest[:16]}.json"
        path = self._evidence_dir / name
        if not path.exists():
            envelope = {SHA_KEY: digest, "evidence": payload}
            path.write_text(
                json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        return Evidence(
            method=evidence.method,
            output=evidence.output,
            timestamp=evidence.timestamp,
            artifact=f"evidence/{name}",
            result=evidence.result,
        )

    # ---------------------------------------------------------- read back

    def read_back(self, artifact: str) -> dict[str, Any]:
        """Read one artifact and re-verify its integrity digest."""
        path = self._artifact_path(artifact)
        if not path.exists():
            raise VerificationError(f"artifact {artifact!r} does not exist — nothing was recorded")
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if SHA_KEY not in envelope or "evidence" not in envelope:
            raise VerificationError(f"artifact {artifact!r} is not a verification envelope")
        payload = json.dumps(
            envelope["evidence"], ensure_ascii=False, sort_keys=True, indent=2
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if digest != envelope[SHA_KEY]:
            raise VerificationError(
                f"artifact {artifact!r} failed its integrity digest "
                f"({envelope[SHA_KEY][:12]} != {digest[:12]})"
            )
        # The five §20.3 fields, verbatim, must survive the roundtrip.
        for key in ("method", "output", "timestamp", "artifact", "result"):
            if key not in envelope["evidence"]:
                raise VerificationError(f"artifact {artifact!r} lost its {key!r} field")
        return envelope

    # ------------------------------------------------------------ report

    def persist_report(self, report: dict[str, Any], name: str = "report.json") -> str:
        """Persist a whole verification report; returns the artifact id."""
        path = self.root / name
        if path.resolve().parent != self.root.resolve():
            raise VerificationError(f"report name {name!r} escapes the store root")
        envelope = {
            "sha256": hashlib.sha256(
                json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
            ).hexdigest(),
            "written_at": utc_now_iso(),
            "report": report,
        }
        path.write_text(
            json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return path.name

    def count(self) -> int:
        """How many evidence artifacts exist (the proof volume)."""
        return sum(1 for _ in self._evidence_dir.glob("ev-*.json"))


__all__ = ["EvidenceStore", "ResultStatus", "SHA_KEY"]
