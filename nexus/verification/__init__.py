"""NEXUS Verification Engine (New Plan §20 — PHASE 20).

*لا يكفي أن NEXUS يعمل — يجب أن يثبت أنه يعمل.*
(It is not enough that NEXUS works — it must prove that it works.)

The four §20.1 nouns behind one contract::

    Verifier   Evidence   Criterion   Result

The nine §20.2 domains, each with its own verifier::

    Software   Windows   Browser   Documents   Research
    Git   Memory   Models   System

The §20.3 evidence — five fields on every observation::

    method   output   timestamp   artifact   result

The §20.4 repair loop, verbatim and ordered::

    Fail → Diagnose → Fix → Retest → Verify

Every criterion's proof is persisted as a sha256-sealed JSON artifact
(:class:`EvidenceStore`), every SKIP is an honest refusal (the Windows
facts are judged on the real box), and no capability row is invented
without proof — the matrix law applied to NEXUS itself.

Stdlib only.
"""

from __future__ import annotations

from .contracts import (
    REPAIR_STAGES,
    VERIFICATION_DOMAINS,
    Criterion,
    CriterionError,
    CriterionSkipped,
    Evidence,
    Result,
    ResultStatus,
    VerificationError,
    Verifier,
    check_sha256,
    utc_now_iso,
)
from .domains import (
    BaseVerifier,
    BrowserVerifier,
    DocumentsVerifier,
    GitVerifier,
    MemoryVerifier,
    ModelsVerifier,
    ResearchVerifier,
    SoftwareVerifier,
    SystemVerifier,
    WindowsVerifier,
    make_verifiers,
)
from .engine import (
    OVERALL_DEGRADED,
    OVERALL_FAIL,
    OVERALL_PASS,
    DomainTally,
    VerificationEngine,
    VerificationReport,
)
from .evidence import EvidenceStore
from .repair import (
    Attempt,
    CreateDirectoryStrategy,
    Diagnosis,
    Diagnostician,
    FixReport,
    NoOpStrategy,
    RepairLoop,
    RepairOutcome,
    RepairStrategy,
    RuleDiagnostician,
    StageTrace,
    TransientRetryStrategy,
    UnlockRetryStrategy,
)

__all__ = [
    # §20.1 nouns
    "Criterion",
    "CriterionError",
    "CriterionSkipped",
    "Evidence",
    "Result",
    "ResultStatus",
    "Verifier",
    "VerificationError",
    "VERIFICATION_DOMAINS",
    # engine
    "DomainTally",
    "OVERALL_DEGRADED",
    "OVERALL_FAIL",
    "OVERALL_PASS",
    "VerificationEngine",
    "VerificationReport",
    # evidence
    "EvidenceStore",
    # domains
    "BaseVerifier",
    "BrowserVerifier",
    "DocumentsVerifier",
    "GitVerifier",
    "MemoryVerifier",
    "ModelsVerifier",
    "ResearchVerifier",
    "SoftwareVerifier",
    "SystemVerifier",
    "WindowsVerifier",
    "make_verifiers",
    # repair
    "Attempt",
    "CreateDirectoryStrategy",
    "Diagnosis",
    "Diagnostician",
    "FixReport",
    "NoOpStrategy",
    "REPAIR_STAGES",
    "RepairLoop",
    "RepairOutcome",
    "RepairStrategy",
    "RuleDiagnostician",
    "StageTrace",
    "TransientRetryStrategy",
    "UnlockRetryStrategy",
    # helpers
    "check_sha256",
    "utc_now_iso",
]
