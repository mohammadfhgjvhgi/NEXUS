"""NEXUS Security System (New Plan §21 — PHASE 21).

*Full capability + controlled execution.*

The Spec §156 triad behind one pipeline::

    Scope + Permission + Execution Gate

The ten sections::

    21.1  Scope Engine Integration   — the §3.2/§3.3 scope is the
                                       first check of every admission
    21.2  Permission Engine          — §163 risk × §3.5 policy
    21.3  Tool Gate                  — named tools, declared risks
    21.4  MCP Gate                   — server:tool pairs, allow-lists
    21.5  Plugin Gate                — declared permissions; secrets
                                       never a plugin default
    21.6  Secret Handling            — references out, text never out
    21.7  Redaction                  — [REDACTED:<kind>], patterns
    21.8  Audit                      — Who|What|When|Where|Result
    21.9  Trivy                      — aquasecurity/trivy: dependency
                                       · secret · license · vulnerability
    21.10 Security Rules             — لا يصل secret إلى: Memory ·
                                       Normal chat · Logs · Activity

Bound by the Blueprint §79 law — security is not an obstacle:
explicit policy denial is the only denial; everything else flows or
escalates.  Every verdict is audited (deny included), every
credential is a reference, and the four sinks are guarded at their
doors — structurally, not by discipline.

Stdlib only.
"""

from __future__ import annotations

from .audit import (
    AUDIT_FIELDS,
    ActivityFeed,
    AuditLog,
    AuditRecord,
    co_audit,
    make_activity_feed,
    make_audit_log,
)
from .contracts import (
    ACTION_KINDS,
    CREDENTIAL_FIELDS,
    PROTECTED_SINKS,
    SCAN_KINDS,
    TRIVY_REPOSITORY,
    Credential,
    GateDecision,
    GateVerdict,
    PermissionDeniedError,
    RiskLevel,
    SecretError,
    SecretLeakError,
    SecurityAction,
    SecurityError,
    TrivyUnavailable,
    redact_preview,
)
from .gates import (
    PLUGIN_PERMISSIONS,
    AdmissionReport,
    GatePipeline,
    McpGate,
    McpServer,
    PluginGate,
    PluginRegistration,
    ToolGate,
    ToolRegistration,
    make_pipeline,
)
from .permissions import (
    RISK_CLASSIFICATION,
    PermissionEngine,
    ScopeContext,
    ScopeEngineIntegration,
    classify,
    make_permission_engine,
)
from .redaction import (
    REDACTED_MARK,
    RedactionFinding,
    Redactor,
    make_redactor,
)
from .rules import SecurityRules, make_rules
from .secrets import SecretVault, make_vault
from .trivy import (
    BaselineScanner,
    Finding,
    ScanReport,
    TrivyScanner,
    make_scanner,
)

__all__ = [
    # §21.1–§21.2
    "PermissionEngine",
    "RISK_CLASSIFICATION",
    "ScopeContext",
    "ScopeEngineIntegration",
    "classify",
    "make_permission_engine",
    # §21.3–§21.5
    "AdmissionReport",
    "GatePipeline",
    "McpGate",
    "McpServer",
    "PLUGIN_PERMISSIONS",
    "PluginGate",
    "PluginRegistration",
    "ToolGate",
    "ToolRegistration",
    "make_pipeline",
    # §21.6
    "Credential",
    "CREDENTIAL_FIELDS",
    "SecretVault",
    "make_vault",
    # §21.7
    "REDACTED_MARK",
    "RedactionFinding",
    "Redactor",
    "make_redactor",
    # §21.8
    "AUDIT_FIELDS",
    "ActivityFeed",
    "AuditLog",
    "AuditRecord",
    "co_audit",
    "make_activity_feed",
    "make_audit_log",
    # §21.9
    "BaselineScanner",
    "Finding",
    "SCAN_KINDS",
    "ScanReport",
    "TRIVY_REPOSITORY",
    "TrivyScanner",
    "make_scanner",
    # §21.10
    "PROTECTED_SINKS",
    "SecurityRules",
    "make_rules",
    # nouns + errors
    "ACTION_KINDS",
    "GateDecision",
    "GateVerdict",
    "PermissionDeniedError",
    "RiskLevel",
    "SecretError",
    "SecretLeakError",
    "SecurityAction",
    "SecurityError",
    "TrivyUnavailable",
    "redact_preview",
]
