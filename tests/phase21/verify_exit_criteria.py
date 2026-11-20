#!/usr/bin/env python3
"""Phase 21 security harness — New Plan §21 Exit Gate.

Proves the Security System section by section:

* A — Contracts (§21.1–§21.2): the verbatim vocabulary — the four
      protected sinks · the four scan kinds · aquasecurity/trivy ·
      the three risk levels · the three verdicts — plus the Spec §163
      risk ladder and the Scope Engine integration (§3.3 resolution
      consumed, §3.4 carve audited).
* B — Gates (§21.3–§21.5): Tool · MCP · Plugin — blocked denied,
      unregistered escalated (never silently allowed), MCP allow-lists
      enforced, plugin secrets access never a default, and the full
      v0.1 §57 pipeline admitting one real action end-to-end with
      every verdict audited.
* C — Secrets & Redaction (§21.6–§21.7): the reference law — six §160
      fields, no text on any surface — resolve audited without the
      text, the exact-match scrub catching patternless secrets, and
      the §21.7 patterns (keys · bearer · JWT · URLs · assignments)
      cleaning without touching benign text.
* D — Audit & Trivy (§21.8–§21.9): the five §164 fields verbatim, the
      §165 Audit/Activity split, JSONL artifacts, and the four §21.9
      scan kinds in both honest modes (trivy parse + baseline).
* E — Security Rules (§21.10) + honesty: every one of the four sinks
      refuses pattern-shaped AND vault-exact secrets; the audit log is
      guarded structurally at append; unknown sinks are refused.
* F — Integration + regression: NEXUS_PHASE ≥ 21, nexus-core ≥ 0.21.0,
      the security core stays stdlib-only at module top level, and the
      neighbor phase suites (15–20) stay green (skippable with
      --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        FAILED.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {label} — {type(exc).__name__}: {exc}")
    else:
        PASSED.append(label)
        print(f"  ✓ {label}")


def expects(exc_types: tuple[type, ...] | type, fn, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
    try:
        fn(*args, **kwargs)
    except exc_types:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_types}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exc_types}, nothing raised")


# planted secrets — built by concatenation, never literals
PLANT_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
PLANT_GHP = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyzABCD"
PLANT_PLAIN = "villa-guest-network-passcode-77"


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.core.scope.engine import ScopeEngine
    from nexus.core.workspace.manager import WorkspaceManager
    from nexus.security import (
        ACTION_KINDS,
        PROTECTED_SINKS,
        RISK_CLASSIFICATION,
        SCAN_KINDS,
        TRIVY_REPOSITORY,
        GateVerdict,
        PermissionEngine,
        RiskLevel,
        ScopeEngineIntegration,
        SecurityAction,
        classify,
    )

    def vocabulary_verbatim() -> None:
        assert PROTECTED_SINKS == ("memory", "normal_chat", "logs", "activity")
        assert SCAN_KINDS == ("dependency", "secret", "license", "vulnerability")
        assert TRIVY_REPOSITORY == "aquasecurity/trivy"
        assert {r.value for r in RiskLevel} == {"low", "medium", "high"}
        assert {v.value for v in GateVerdict} == {"allow", "confirm", "deny"}
        assert "tool" in ACTION_KINDS and "mcp" in ACTION_KINDS and "plugin" in ACTION_KINDS

    def risk_ladder_verbatim() -> None:
        assert RISK_CLASSIFICATION == (
            ("read file", "read", RiskLevel.LOW),
            ("edit file", "write", RiskLevel.MEDIUM),
            ("delete file", "delete", RiskLevel.HIGH),
            ("run unrestricted command", "execute_unrestricted", RiskLevel.HIGH),
            ("push release", "push_release", RiskLevel.HIGH),
        )
        assert classify(SecurityAction(kind="command", name="any")) is RiskLevel.HIGH

    def scope_integration() -> None:
        work = Path(tempfile.mkdtemp(prefix="p21-gate-a-"))
        (work / "in.txt").write_text("x\n", encoding="utf-8")
        manager = WorkspaceManager(Path(tempfile.mkdtemp(prefix="p21-gate-ws-")))
        manager.register(name="GateA", path=str(work))
        integration = ScopeEngineIntegration(ScopeEngine())
        context = integration.scope_for(str(work / "in.txt"), manager=manager)
        assert context.workspace_id == manager.list_workspaces()[0].id
        decision = PermissionEngine().decide(
            SecurityAction(kind="file", name="read", target=str(work / "in.txt")),
            scope=context.scope,
        )
        assert decision.allowed and decision.risk is RiskLevel.LOW

    check("A1 · §21.10/§21.9/§163 vocabulary verbatim", vocabulary_verbatim)
    check("A2 · the §163 risk ladder verbatim + classify", risk_ladder_verbatim)
    check("A3 · §21.1 scope resolution consumed by a real decision", scope_integration)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.core.policy.models import AutonomyLevel, TaskPolicy
    from nexus.core.scope.models import Scope
    from nexus.security import (
        AuditLog,
        GatePipeline,
        GateVerdict,
        McpGate,
        PluginGate,
        RiskLevel,
        SecurityAction,
        ToolGate,
    )

    def tool_gate() -> None:
        gate = ToolGate(blocked=["format-disk"])
        gate.register("editor", risk=RiskLevel.LOW)
        blocked = gate.evaluate(SecurityAction(kind="tool", name="format-disk"))
        assert blocked.verdict is GateVerdict.DENY
        ok = gate.evaluate(SecurityAction(kind="tool", name="editor"))
        assert ok.verdict is GateVerdict.ALLOW
        escalated = gate.evaluate(SecurityAction(kind="tool", name="ghost-tool"))
        assert escalated.verdict is GateVerdict.CONFIRM and "not registered" in escalated.reason

    def mcp_gate() -> None:
        gate = McpGate(blocked_servers=["rogue-mcp"])
        gate.register("fs-mcp", tools=["read_file"])
        rogue = gate.evaluate(SecurityAction(kind="mcp", name="rogue-mcp:read_file"))
        assert rogue.verdict is GateVerdict.DENY
        ok = gate.evaluate(SecurityAction(kind="mcp", name="fs-mcp:read_file"))
        assert ok.verdict is GateVerdict.ALLOW
        outside = gate.evaluate(SecurityAction(kind="mcp", name="fs-mcp:wipe_all"))
        assert outside.verdict is GateVerdict.CONFIRM

    def plugin_gate() -> None:
        gate = PluginGate()
        gate.register("helper", permissions=["memory"])
        denied = gate.evaluate(SecurityAction(kind="plugin", name="helper", target="secrets"))
        assert denied.verdict is GateVerdict.DENY and denied.risk is RiskLevel.HIGH
        gate.register("reader", permissions=["secrets"], secrets_granted=True)
        granted = gate.evaluate(SecurityAction(kind="plugin", name="reader", target="secrets"))
        assert granted.verdict is GateVerdict.ALLOW

    def pipeline_end_to_end() -> None:
        audit = AuditLog()
        tool_gate = ToolGate(blocked=["bad-tool"])
        tool_gate.register("editor", risk=RiskLevel.LOW)
        pipeline = GatePipeline(tool_gate=tool_gate, audit=audit)
        allowed = pipeline.admit(
            SecurityAction(kind="tool", name="editor"), policy=TaskPolicy.default()
        )
        denied = pipeline.admit(
            SecurityAction(kind="tool", name="bad-tool"), policy=TaskPolicy.default()
        )
        confirm_policy = TaskPolicy.default()
        confirm_policy.autonomy_level = AutonomyLevel.SUGGEST
        confirmed = pipeline.admit(
            SecurityAction(kind="file", name="edit", target="C:\\x\\y.txt"),
            policy=confirm_policy,
            scope=Scope.empty(),
        )
        assert allowed.allowed and not denied.allowed
        assert confirmed.final is not None and confirmed.final.requires_confirmation
        assert audit.size() == 3
        assert {r.result for r in audit.history()} == {"allow", "deny", "confirm"}

    check("B1 · §21.3 Tool Gate: blocked/unregistered/allowed", tool_gate)
    check("B2 · §21.4 MCP Gate: server + tool allow-list", mcp_gate)
    check("B3 · §21.5 Plugin Gate: secrets never a default", plugin_gate)
    check("B4 · the §57 pipeline: allow/deny/confirm, all audited", pipeline_end_to_end)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from nexus.security import (
        CREDENTIAL_FIELDS,
        Credential,
        SecretError,
        make_redactor,
        make_vault,
    )

    def reference_law() -> None:
        import dataclasses

        assert tuple(f.name for f in dataclasses.fields(Credential)) == CREDENTIAL_FIELDS
        vault = make_vault()
        credential = vault.store("github", PLANT_GHP, scope="task")
        assert credential.reference.startswith("vault://github/")
        rendered = str(credential.as_dict()) + repr(vault) + json.dumps(vault.as_dict())
        assert PLANT_GHP not in rendered

    def resolve_audited_and_scrubbed() -> None:
        vault = make_vault()
        credential = vault.store("legacy", PLANT_PLAIN)
        assert vault.resolve(credential.id) == PLANT_PLAIN
        assert vault.get(credential.id).last_used != ""
        assert PLANT_PLAIN not in json.dumps(vault.audit_trail())
        clean, hits = vault.scrub(f"use {PLANT_PLAIN} now")
        assert hits == 1 and PLANT_PLAIN not in clean
        expects((SecretError,), vault.resolve, "vault://x/sec_none")

    def redaction_patterns() -> None:
        redactor = make_redactor()
        dirty = (
            f"aws {PLANT_AWS} · github {PLANT_GHP} · "
            "Authorization: Bearer abcdef0123456789abcdef · "
            "https://user:hunter2pass@github.com/a/b.git"
        )
        clean, count = redactor.redact(dirty)
        assert count >= 4
        assert PLANT_AWS not in clean and PLANT_GHP not in clean
        assert "hunter2pass" not in clean and "abcdef0123456789" not in clean
        benign = "M:\\NEXUS works · pytest green · delete file = high risk"
        assert redactor.redact(benign) == (benign, 0)

    check("C1 · §21.6 reference law: six fields, no text anywhere", reference_law)
    check("C2 · resolve audited text-free + exact-match scrub", resolve_audited_and_scrubbed)
    check("C3 · §21.7 patterns clean; benign text untouched", redaction_patterns)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.security import (
        AUDIT_FIELDS,
        ActivityFeed,
        AuditLog,
        AuditRecord,
        BaselineScanner,
        ScanReport,
        TrivyScanner,
        make_audit_log,
        make_redactor,
    )

    def audit_five_fields_and_jsonl() -> None:
        assert AUDIT_FIELDS == ("who", "what", "when", "where", "result")
        log = make_audit_log()
        log.append(AuditRecord(who="agent", what="file:delete", where="M:/x", result="confirm"))
        target = log.write_jsonl(Path(tempfile.mkdtemp(prefix="p21-gate-d-")) / "a.jsonl")
        record = json.loads(target.read_text(encoding="utf-8").strip())
        assert tuple(record)[:5] == AUDIT_FIELDS

    def audit_vs_activity() -> None:
        guard = make_redactor().redact_to_safe
        audit = AuditLog(guard=guard)
        activity = ActivityFeed(guard=guard)
        audit.append(AuditRecord(who="agent", what="git:push", where="dev", result="allow"))
        activity.post("Pushed 1 commit to develop ✓")
        assert len(audit) == 1 and len(activity) == 1
        assert isinstance(audit.history()[0], AuditRecord)
        assert isinstance(activity.items()[0], str)

    def trivy_both_modes() -> None:
        root = Path(tempfile.mkdtemp(prefix="p21-gate-t-"))
        (root / "requirements.txt").write_text("requests==2.19.0\n", encoding="utf-8")
        (root / "app.py").write_text(f"K = '{PLANT_AWS}'\n", encoding="utf-8")
        baseline = BaselineScanner()
        reports = baseline.scan_all(root)
        assert tuple(reports) == ("dependency", "secret", "license", "vulnerability")
        assert {f.rule_id for f in reports["secret"].findings} >= {"aws_access_key"}
        assert reports["vulnerability"].count == 0 and reports["vulnerability"].notes
        rendered = json.dumps(reports["secret"].as_dict())
        assert PLANT_AWS not in rendered  # the scanner never re-prints it
        scanner = TrivyScanner(binary="/nonexistent/trivy")
        assert scanner.available() is False
        expects((Exception,), scanner.scan, root, "secret")
        for report in reports.values():
            assert isinstance(report, ScanReport)

    check("D1 · §21.8 five fields verbatim + JSONL artifact", audit_five_fields_and_jsonl)
    check("D2 · §165 Audit vs Activity are separate surfaces", audit_vs_activity)
    check("D3 · §21.9 four kinds × two honest modes (no re-printed secrets)", trivy_both_modes)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from nexus.security import (
        PROTECTED_SINKS,
        SecretLeakError,
        SecurityError,
        make_rules,
    )

    def four_doors_refuse() -> None:
        rules = make_rules()
        rules.vault.store("legacy", PLANT_PLAIN, scope="task")
        for sink in PROTECTED_SINKS:
            for dirty in (f"key {PLANT_AWS}", f"pass {PLANT_PLAIN}"):
                clean = rules.guard(sink, dirty)
                assert PLANT_AWS not in clean and PLANT_PLAIN not in clean, sink

    def unknown_sink_refused() -> None:
        rules = make_rules()
        expects((SecurityError,), rules.guard, "telemetry", "x")

    def hard_stop_exists() -> None:
        rules = make_rules()
        rules.vault.store("legacy", PLANT_PLAIN, scope="task")
        rules.assert_clean("clean payload")
        expects((SecretLeakError,), rules.assert_clean, f"carry {PLANT_AWS}")
        expects((SecretLeakError,), rules.assert_clean, f"carry {PLANT_PLAIN}")

    check("E1 · §21.10 all four sinks refuse pattern+exact secrets", four_doors_refuse)
    check("E2 · an unknown sink is refused (exactly four doors)", unknown_sink_refused)
    check("E3 · assert_clean is the belt-and-braces hard stop", hard_stop_exists)


# ------------------------------------------------------------------- section F


def section_f() -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 21, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
        major, minor, _ = (int(p) for p in nexus.__version__.split("."))
        assert (major, minor) >= (0, 21), f"version {nexus.__version__}"

    def stdlib_only_top_level() -> None:
        pkg = ROOT / "nexus" / "security"
        for py in pkg.glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.level > 0:
                        continue  # relative — nexus's own
                    roots = (
                        [a.name.split(".")[0] for a in node.names]
                        if isinstance(node, ast.Import)
                        else [str(node.module or "").split(".")[0]]
                    )
                    for root in roots:
                        assert root in sys.stdlib_module_names | {"nexus"} or root == "", (
                            f"{py.name}: non-stdlib top-level import {root!r}"
                        )

    def regression() -> None:
        if NO_REGRESSION:
            print("      (skipped by --no-regression)")
            return
        for phase in (15, 16, 17, 18, 19, 20):
            suite = ROOT / "tests" / f"phase{phase:02d}"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(suite), "-q", "-p", "no:cacheprovider",
                 "--ignore-glob=*test_device_proof*", "--ignore-glob=*live_*"],
                capture_output=True, text=True, timeout=560, cwd=str(ROOT),
            )
            assert proc.returncode == 0, f"phase {phase} regression failed:\n{proc.stdout[-1500:]}"

    check("F1 · NEXUS_PHASE ≥ 21 and nexus-core ≥ 0.21.0", identity)
    check("F2 · the security core stays stdlib-only at top level", stdlib_only_top_level)
    check("F3 · neighbor suites 15–20 stay green", regression)


# ----------------------------------------------------------------------- main

NO_REGRESSION = False


def main() -> int:
    global NO_REGRESSION
    parser = argparse.ArgumentParser(description="Phase 21 exit gate")
    parser.add_argument("--no-regression", action="store_true")
    args = parser.parse_args()
    NO_REGRESSION = args.no_regression

    print("PHASE 21 — Security System — Exit Gate")
    for section, title in (
        (section_a, "A · Contracts & vocabulary (§21.1–§21.2 · §163 · §21.10)"),
        (section_b, "B · Gates (§21.3–§21.5)"),
        (section_c, "C · Secrets & Redaction (§21.6–§21.7)"),
        (section_d, "D · Audit & Trivy (§21.8–§21.9)"),
        (section_e, "E · Security Rules (§21.10) + honesty"),
        (section_f, "F · Integration + regression"),
    ):
        print(f"\n[{title}]")
        section()

    print(f"\nGATE: {len(PASSED)} passed · {len(FAILED)} failed")
    if FAILED:
        for line in FAILED:
            print(f"  ✗ {line}")
        return 1
    print("EXIT CRITERIA: Implemented · Integrated · Tested · Verified · Documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
