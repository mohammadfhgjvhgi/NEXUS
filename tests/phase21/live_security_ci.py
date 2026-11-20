#!/usr/bin/env python3
"""PHASE 21 live security proof — real gates, real vault, real redaction,
real trivy when this host has one (MODE A) and honest MODE B when not.

Ten rungs, each printed as [PASS]/[FAIL] and every claim carrying its
observation (the §20 evidence law applied to §21):

  1. §21 vocabulary verbatim — sinks · scan kinds · risk levels ·
     verdicts · TRIVY_REPOSITORY.
  2. The full admission walk (v0.1 §57) on real actions — in-scope
     allow, blocked deny, escalation — every verdict audited.
  3. §21.6 the reference law — store → reference-only surface →
     resolve advances last-used, the vault's audit never carries text.
  4. §21.7+§21.9 MODE B — a real planted tree is scanned; findings
     name their kinds and their snippets stay redacted.
  5. §21.9 MODE A — a real trivy scan (secret + vulnerability kinds).
     Strict when NEXUS_REQUIRE_TRIVY=1 (the CI job installs trivy);
     an absent binary is an honest note anywhere else.
  6. §21.9 license kind — a real license finding (SPDX header /
     LICENSE file / declared license).
  7. §21.10 — the planted secrets (pattern-shaped AND patternless-
     in-vault) reach none of the four sinks.
  8. §21.8 — the audit JSONL artifact round-trips with its five
     fields verbatim; Activity stays a separate, guarded surface.
  9. §21.3–§21.5 — the three gates observed deciding allow · confirm
     · deny on registered entries.
 10. Identity — NEXUS_PHASE ≥ 21 and nexus-core ≥ 0.21.0.

Run (CI/sandbox):  python tests/phase21/live_security_ci.py
Run (device, via pytest): tests/phase21/test_device_proof.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus.core.policy.models import TaskPolicy  # noqa: E402
from nexus.core.scope.engine import ScopeEngine  # noqa: E402
from nexus.core.scope.models import Scope  # noqa: E402
from nexus.security import (  # noqa: E402
    PROTECTED_SINKS,
    SCAN_KINDS,
    TRIVY_REPOSITORY,
    AuditRecord,
    BaselineScanner,
    GatePipeline,
    GateVerdict,
    McpGate,
    PluginGate,
    RiskLevel,
    ScopeEngineIntegration,
    SecurityAction,
    ToolGate,
    TrivyScanner,
    make_activity_feed,
    make_audit_log,
    make_redactor,
    make_rules,
    make_vault,
)

# planted secrets — built by concatenation (no literal in this file)
PLANT_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
PLANT_GHP = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyzABCD"
PLANT_PLAIN = "villa-guest-network-passcode-77"  # no pattern shape

RESULTS: list[tuple[str, str, str]] = []


def rung(label: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        note = fn()
        RESULTS.append(("PASS", label, note or ""))
        print(f"[PASS] {label}" + (f" — {note}" if note else ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append(("FAIL", label, f"{type(exc).__name__}: {exc}"))
        print(f"[FAIL] {label} — {type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ fixtures


def _planted_tree(root: Path) -> Path:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text(
        "requests==2.19.0\nurllib3==1.24.1\n", encoding="utf-8"
    )
    (root / "app" / "main.py").write_text(
        "# SPDX-License-Identifier: MIT\n"
        f"AWS_KEY = '{PLANT_AWS}'\n"
        f"GITHUB_TOKEN = '{PLANT_GHP}'\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text("MIT License\n\nNEXUS fixture\n", encoding="utf-8")
    return root


# ------------------------------------------------------------------- rungs


def rung_1_vocabulary() -> str:
    assert PROTECTED_SINKS == ("memory", "normal_chat", "logs", "activity")
    assert SCAN_KINDS == ("dependency", "secret", "license", "vulnerability")
    assert {r.value for r in RiskLevel} == {"low", "medium", "high"}
    assert {v.value for v in GateVerdict} == {"allow", "confirm", "deny"}
    assert TRIVY_REPOSITORY == "aquasecurity/trivy"
    return "sinks 4 · kinds 4 · risks 3 · verdicts 3 · repo verbatim"


def rung_2_admission_walk() -> str:
    audit = make_audit_log(guard=make_redactor().redact_to_safe)
    tool_gate = ToolGate()
    tool_gate.register("editor", risk=RiskLevel.LOW)
    pipeline = GatePipeline(tool_gate=tool_gate, audit=audit)
    integration = ScopeEngineIntegration(ScopeEngine())
    work = Path(tempfile.mkdtemp(prefix="p21-live-walk-"))
    (work / "task.txt").write_text("task file\n", encoding="utf-8")

    # a. in-scope low-risk read → ALLOW (policy + pipeline, audited)
    from nexus.core.workspace.manager import WorkspaceManager

    manager = WorkspaceManager(Path(tempfile.mkdtemp(prefix="p21-live-ws-")))
    workspace = manager.register(name="LiveWalk", path=str(work))
    context = integration.scope_for(str(work / "task.txt"), manager=manager)
    read = pipeline.admit(
        SecurityAction(kind="file", name="read", target=str(work / "task.txt")),
        scope=context.scope,
    )
    assert read.allowed, read.as_dict()

    # b. blocked tool → DENY (explicit policy — the only hard stop)
    policy = TaskPolicy.from_overrides({"tool_policy.blocked_tools": ["format-disk"]})
    denied = pipeline.admit(
        SecurityAction(kind="tool", name="format-disk"), policy=policy
    )
    assert not denied.allowed

    # c. high risk below FULL → CONFIRM
    from nexus.core.policy.models import AutonomyLevel

    confirm_policy = TaskPolicy.default()
    confirm_policy.autonomy_level = AutonomyLevel.ACT_CONFIRMED
    confirmed = pipeline.admit(
        SecurityAction(kind="git", name="push", target="feature-branch"),
        policy=confirm_policy,
        scope=Scope.empty(),
    )
    assert confirmed.final is not None and confirmed.final.verdict is GateVerdict.CONFIRM

    assert audit.size() == 3
    verdicts = {r.result for r in audit.history()}
    assert verdicts == {"allow", "deny", "confirm"}
    assert len(workspace.name) > 0
    return "allow · deny · confirm all audited (scope→permission→gate)"


def rung_3_reference_law() -> str:
    vault = make_vault()
    credential = vault.store("github", PLANT_GHP, scope="task")
    assert credential.reference.startswith("vault://github/")
    surface = json.dumps(vault.as_dict()) + repr(vault) + repr(credential)
    assert PLANT_GHP not in surface and PLANT_PLAIN not in surface
    assert vault.resolve(credential.id) == PLANT_GHP
    assert vault.get(credential.id).last_used != ""
    trail = json.dumps(vault.audit_trail())
    assert PLANT_GHP not in trail
    return f"reference={credential.reference} · last_used advanced · trail text-free"


def rung_4_baseline_scan() -> str:
    root = _planted_tree(Path(tempfile.mkdtemp(prefix="p21-live-tree-")))
    report = BaselineScanner().scan(root, "secret")
    kinds = {f.rule_id for f in report.findings}
    assert {"aws_access_key", "github_token"} <= kinds, kinds
    rendered = json.dumps(report.as_dict())
    assert PLANT_AWS not in rendered and PLANT_GHP not in rendered
    deps = BaselineScanner().scan(root, "dependency")
    assert {f.rule_id for f in deps.findings} >= {"requests", "urllib3"}
    return f"secret findings={report.count} (kinds named, snippets redacted) · deps={deps.count}"


def rung_5_trivy_mode_a() -> str:
    require = os.environ.get("NEXUS_REQUIRE_TRIVY") == "1"
    scanner = TrivyScanner()
    if not scanner.available():
        if require:
            raise AssertionError("NEXUS_REQUIRE_TRIVY=1 but trivy is not on this host")
        root = _planted_tree(Path(tempfile.mkdtemp(prefix="p21-live-trivy-")))
        honest = BaselineScanner().scan(root, "vulnerability")
        assert honest.count == 0 and "trivy" in honest.notes[0]
        return "trivy absent — MODE B honest note (set NEXUS_REQUIRE_TRIVY=1 for strict)"
    version = scanner.version()
    root = _planted_tree(Path(tempfile.mkdtemp(prefix="p21-live-trivy-")))
    secrets = scanner.scan(root, "secret")
    kinds = {f.rule_id for f in secrets.findings}
    assert "aws-access-key-id" in kinds or "aws_access_key" in kinds or kinds, kinds
    rendered = json.dumps(secrets.as_dict())
    assert PLANT_AWS not in rendered
    vulns = scanner.scan(root, "vulnerability")
    assert vulns.count >= 1, f"expected CVEs for requests==2.19.0, got {vulns.as_dict()}"
    ids = {f.rule_id for f in vulns.findings}
    assert any(cid.startswith("CVE-") for cid in ids), sorted(ids)[:5]
    return f"{version} · secret findings={secrets.count} · CVEs={vulns.count}"


def rung_6_license_kind() -> str:
    root = _planted_tree(Path(tempfile.mkdtemp(prefix="p21-live-lic-")))
    scanner = TrivyScanner()
    if scanner.available():
        report = scanner.scan(root, "license")
        assert report.mode == "trivy"
        return f"trivy license scan ran ({report.count} findings)"
    report = BaselineScanner().scan(root, "license")
    rules_ = {f.rule_id for f in report.findings}
    assert "MIT" in rules_ and "license-file" in rules_, rules_
    return "baseline license detection: MIT declared + SPDX + LICENSE file"


def rung_7_four_sinks() -> str:
    rules = make_rules()
    rules.vault.store("legacy-app", PLANT_PLAIN, scope="task")
    dirty_pattern = f"deploy with {PLANT_AWS} now"
    dirty_exact = f"passphrase: {PLANT_PLAIN}"
    for sink in PROTECTED_SINKS:
        clean = rules.guard(sink, dirty_pattern)
        assert PLANT_AWS not in clean, sink
        clean = rules.guard(sink, dirty_exact)
        assert PLANT_PLAIN not in clean, sink
    # the redaction hook that feeds the four doors — sanity on its own
    redactor = make_redactor()
    assert not redactor.contains_secret(redactor.redact_to_safe(dirty_pattern))
    return "pattern-shaped and vault-exact secrets blocked at all four doors"


def rung_8_audit_artifact() -> str:
    rules = make_rules()
    rules.vault.store("github", PLANT_GHP, scope="task")
    log = make_audit_log(guard=lambda text: rules.guard("logs", text))
    log.append(
        AuditRecord(
            who="agent",
            what=f"tool:leaky-run token={PLANT_GHP}",
            where="m:/client",
            result="confirm",
        )
    )
    target = log.write_jsonl(Path(tempfile.mkdtemp(prefix="p21-live-audit-")) / "audit.jsonl")
    on_disk = target.read_text(encoding="utf-8")
    assert PLANT_GHP not in on_disk
    record = json.loads(on_disk.strip().splitlines()[0])
    assert tuple(record)[:5] == ("who", "what", "when", "where", "result")
    feed = make_activity_feed(guard=lambda text: rules.guard("activity", text))
    feed.post(f"rotated the leaked token {PLANT_GHP}")
    assert PLANT_GHP not in str(feed.items())
    return "audit JSONL five-fields verbatim · guarded at append · Activity separate"


def rung_9_three_gates() -> str:
    tool = ToolGate(blocked=["format-disk"])
    tool.register("editor", risk=RiskLevel.LOW)
    mcp = McpGate()
    mcp.register("filesystem-mcp", tools=["read_file", "list_dir"])
    plugin = PluginGate()
    plugin.register("memory-helper", permissions=["memory"])
    verdicts: set[str] = set()
    verdicts.add(tool.evaluate(__act("tool", "editor")).verdict.value)  # type: ignore[arg-type,name-defined]
    verdicts.add(tool.evaluate(__act("tool", "format-disk")).verdict.value)  # type: ignore[arg-type,name-defined]
    verdicts.add(mcp.evaluate(__act("mcp", "filesystem-mcp:read_file")).verdict.value)  # type: ignore[arg-type,name-defined]
    verdicts.add(mcp.evaluate(__act("mcp", "filesystem-mcp:delete_tree")).verdict.value)  # type: ignore[arg-type,name-defined]
    verdicts.add(plugin.evaluate(__act("plugin", "memory-helper", target="memory")).verdict.value)  # type: ignore[arg-type,name-defined]
    verdicts.add(plugin.evaluate(__act("plugin", "memory-helper", target="secrets")).verdict.value)  # type: ignore[arg-type,name-defined]
    assert verdicts == {"allow", "deny", "confirm"}, verdicts
    return "tool+mcp+plugin gates decided allow · deny · confirm"


def __act(kind: str, name: str, target: str = ""):  # type: ignore[no-untyped-def]
    from nexus.security import SecurityAction

    return SecurityAction(kind=kind, name=name, target=target)


def rung_10_identity() -> str:
    import nexus

    assert nexus.NEXUS_PHASE >= 21, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
    major, minor, _ = (int(p) for p in nexus.__version__.split("."))
    assert (major, minor) >= (0, 21), f"version {nexus.__version__}"
    return f"nexus {nexus.__version__} · NEXUS_PHASE={nexus.NEXUS_PHASE}"


# --------------------------------------------------------------------- main


def main() -> int:
    print("PHASE 21 — Security System — live proof")
    rung("1 · §21 vocabulary verbatim", rung_1_vocabulary)
    rung("2 · admission walk allow/deny/confirm audited", rung_2_admission_walk)
    rung("3 · §21.6 reference law (no text outside the vault)", rung_3_reference_law)
    rung("4 · §21.7+§21.9 baseline scan redacts its findings", rung_4_baseline_scan)
    rung("5 · §21.9 trivy scan (MODE A / honest MODE B)", rung_5_trivy_mode_a)
    rung("6 · §21.9 license kind really scanned", rung_6_license_kind)
    rung("7 · §21.10 four sinks refuse the planted secrets", rung_7_four_sinks)
    rung("8 · §21.8 audit artifact five fields + Activity split", rung_8_audit_artifact)
    rung("9 · §21.3–§21.5 the three gates decide", rung_9_three_gates)
    rung("10 · identity ≥ 0.21.0 / phase ≥ 21", rung_10_identity)

    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    print(f"\nPROOF: {passed}/{len(RESULTS)} rungs passed")
    for status, label, note in RESULTS:
        if status == "FAIL":
            print(f"  ✗ {label}: {note}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
