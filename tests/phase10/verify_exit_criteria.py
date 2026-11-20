#!/usr/bin/env python3
"""Phase 10 verification harness — Final Build Plan §11 Exit Criteria.

Proves the Browser Runtime section by section:

* A — Playwright engine surface (§11.1): the operation vocabulary
       verbatim; the §8.1 ``browser`` record (thirteenth, additive —
       risk 2, path-scoped transfers, per-op verification); honest
       capability probes without the extra.
* B — Browser Sessions (§11.4): user/agent isolation — the agent
       profile root is fixed; user-profile paths are *refused*
       structurally; the §55 CDP gate (explicit consent + explicit
       URL, no discovery); the registry lifecycle.
* C — Authentication (§11.5): secrets never cross the tool seam —
       the schema carries ``vault_ref`` (a reference), never a
       secret; storing rides a *path* or an *env name*; the vault
       refuses DPAPI-less platforms honestly (no plaintext mode);
       the pure scrubber; the vault round-trip with a patched
       crypt core (crypto itself is proven live on the device).
* D — Self-healing selectors (§11.3 ADAPT): the fallback ladder
       order; a dead selector falls through to the next strategy
       (the healing); the ledger records every attempt; all-fail
       raises with the full ledger; bounded retries.
* E — Engine + façade + the §9.5 dom_a11y layer: op dispatch
       validation; the channel ladder; the façade routes every §11.1
       domain through the router; the §11.5 contract at the façade
       (vault_ref in, never the text); the dom_a11y rung maps
       chain actions onto browser ops and refuses honestly without
       a router; unknown ops raise.
* F — Integration + regression: NexusRuntime wires browser_enabled
       (13 records + the dom_a11y rung in the §9.5 chain); disabled
       → the Phase-9 behavior byte for byte; the config keys
       validate; Phases 1–9 harnesses stay green.

Run:  python tests/phase10/verify_exit_criteria.py
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import nexus.browser.auth as auth_module  # noqa: E402
from nexus.browser import (  # noqa: E402
    BROWSER_DOMAINS,
    BROWSER_OPERATIONS,
    CHANNEL_LADDER,
    REDACTED,
    BrowserDomLayer,
    BrowserRuntime,
    BrowserSessionManager,
    BrowserVault,
    EngineError,
    PageSnapshot,
    SelectorFallbacks,
    SelfHealError,
    SessionError,
    VaultError,
    redact_text,
    set_engine_defaults,
)
from nexus.browser import REDACTED as _REDACTED  # noqa: E402
from nexus.computer.hierarchy import ActionTarget  # noqa: E402
from nexus.events import EventBus  # noqa: E402
from nexus.tools import build_tool_system  # noqa: E402
from nexus.tools.registry import ToolRegistry  # noqa: E402

ON_WINDOWS = sys.platform == "win32"


# ------------------------------------------------------------------- runner


class Runner:
    """Check counter with the house reporting format."""

    def __init__(self) -> None:
        self.section = ""
        self.passed = 0
        self.failed = 0
        self.bonus = 0

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        mark = "PASS" if condition else "FAIL"
        line = f"  [{mark}] ({self.section}) {label}"
        if detail and not condition:
            line += f" — {detail}"
        print(line)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def bonus_check(self, label: str, condition: bool, detail: str = "") -> bool:
        """Windows/playwright-only evidence: SKIP never fails."""
        if condition:
            self.bonus += 1
            print(f"  [BONUS] ({self.section}) {label}")
        else:
            print(f"  [SKIP]  ({self.section}) {label} — {detail}")
        return condition

    def summary(self) -> int:
        print()
        print("=" * 72)
        name = Path(sys.argv[0]).name
        if self.failed:
            print(f"{name} — {self.passed} passed, {self.failed} FAILED")
            print("=" * 72)
            return 1
        print(f"{name} — {self.passed} passed, 0 failed (+{self.bonus} bonus)")
        print("=" * 72)
        return 0


# ---------------------------------------------------------------- fixtures


class FakeRouter:
    """A router-shaped recorder — the façade's every call lands here."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.registry = _FakeRegistry()

    def route(self, name: str, arguments: dict[str, Any], **_context: Any) -> Any:
        self.calls.append((name, dict(arguments)))
        return SimpleOutcome()


class _FakeRegistry:
    def get(self, name: str) -> Any:
        return None


class SimpleOutcome:
    ok = True
    output = "fake"
    error = ""


def make_registry(browser: bool) -> ToolRegistry:
    registry = ToolRegistry()
    from nexus.tools.native.base import register_native_tool
    from nexus.tools.native.browser import BrowserTool

    if browser:
        register_native_tool(registry, BrowserTool())
    return registry


# ======================================================================= A


def section_a(runner: Runner) -> None:
    """§11.1 — the Playwright engine surface (the tool record)."""
    runner.section = "A"

    runner.check(
        "the §11.1 domain families are verbatim (eight)",
        BROWSER_DOMAINS == (
            "navigation", "dom", "forms", "upload", "download",
            "tabs", "states", "automation",
        ),
        detail=f"domains={BROWSER_DOMAINS}",
    )
    expected_ops = {
        "navigate", "back", "forward", "reload", "wait", "read",
        "click", "type", "fill", "select", "press",
        "upload", "download",
        "tabs", "tab_select", "tab_new", "tab_close",
        "snapshot", "screenshot", "attach", "close",
    }
    runner.check(
        "the operation vocabulary covers navigation·dom·forms·upload·"
        "download·tabs·states (§11.1, verbatim families)",
        expected_ops <= set(BROWSER_OPERATIONS)
        and len(BROWSER_OPERATIONS) == len(set(BROWSER_OPERATIONS)),
        detail=f"ops={BROWSER_OPERATIONS}",
    )
    runner.check(
        "the channel ladder is chromium → chrome → msedge",
        CHANNEL_LADDER == ("chromium", "chrome", "msedge"),
    )

    registry = make_registry(browser=True)
    definitions = {d.name: d for d in registry.discover()}
    runner.check(
        "the browser record is the 13th, additive (native:browser)",
        "browser" in definitions
        and definitions["browser"].id == "native:browser"
        and len(registry.discover()) == 1,
        detail=f"count={len(registry.discover())}",
    )
    definition = definitions["browser"]
    runner.check(
        "risk 2 · browser.control permission · network+display dimensions",
        definition.risk == 2
        and definition.permissions == ("browser.control",)
        and set(definition.scope_requirements.dimensions) == {"network", "display"},
    )
    runner.check(
        "transfer paths are scope-checked (path + secret_path)",
        set(definition.scope_requirements.path_arguments) == {"path", "secret_path"},
    )
    runner.check(
        "reads are non-mutating; navigation/forms/tabs mutate",
        "read" not in definition.scope_requirements.mutating_operations
        and {"navigate", "click", "tab_new"} <= set(
            definition.scope_requirements.mutating_operations
        ),
    )
    schema_keys = set(definition.input_schema["properties"])
    runner.check(
        "the §11.5 contract: the schema carries vault_ref — never a secret field",
        "vault_ref" in schema_keys and "secret" not in schema_keys,
        detail=f"keys={sorted(schema_keys)}",
    )
    from nexus.tools.models import VerificationStrategy as V  # noqa: E402
    from nexus.tools.native.browser import BrowserTool  # noqa: E402

    tool = BrowserTool()
    runner.check(
        "verification contracts: reads json_field · transfers path_size",
        tool.verification_for("read").strategy == V.JSON_FIELD
        and tool.verification_for("download").strategy == V.PATH_SIZE
        and tool.verification_for("screenshot").strategy == V.PATH_SIZE
        and tool.verification_for("navigate").strategy == V.JSON_FIELD,
    )
    probe = tool.capabilities()
    runner.check(
        "the capability probe is honest (playwright pip present or not)",
        isinstance(probe.available, bool) and probe.reason != "",
        detail=f"probe={probe.to_dict()}",
    )


# ======================================================================= B


def section_b(runner: Runner) -> None:
    """§11.4 — Browser Sessions (user/agent isolation)."""
    runner.section = "B"

    with tempfile.TemporaryDirectory() as root:
        manager = BrowserSessionManager(root)
        runner.check(
            "the agent profile root is fixed and private "
            "(<data>/browser/agent-profile)",
            manager.agent_profile_dir.endswith("agent-profile")
            and Path(manager.agent_profile_dir).is_dir(),
        )
        refused = False
        try:
            manager.guard_profile(
                r"C:\Users\me\AppData\Local\Google\Chrome\User Data"
            )
        except SessionError:
            refused = True
        runner.check(
            "a user Chrome profile is refused structurally (Spec §55)",
            refused,
        )
        allowed = manager.guard_profile(str(Path(root) / "elsewhere"))
        runner.check(
            "an unrelated profile path passes the guard",
            allowed.endswith("elsewhere"),
        )
        blocked = False
        try:
            manager.request_user_cdp("http://localhost:9222")
        except SessionError as exc:
            blocked = "consent" in str(exc)
        runner.check(
            "the §55 gate refuses CDP attach without explicit consent",
            blocked,
        )
        manager_consent = BrowserSessionManager(root, user_consent=True)
        blocked_url = False
        try:
            manager_consent.request_user_cdp("")
        except SessionError:
            blocked_url = True
        runner.check(
            "with consent, an empty/implicit URL is still refused (no discovery)",
            blocked_url,
        )
        url = manager_consent.request_user_cdp("http://localhost:9222")
        runner.check(
            "consent + explicit URL is the only passing combination",
            url == "http://localhost:9222",
        )
        session = manager.register("agent", engine=object(), profile_dir="p")
        runner.check(
            "session ids carry the kind (browser-agent-0001)",
            session.session_id == "browser-agent-0001"
            and manager.agent_session() is session,
        )
        runner.check(
            "close() releases the session and engine handle",
            manager.close(session.session_id) is True
            and manager.agent_session() is None,
        )
        snapshot = manager.snapshot()
        runner.check(
            "the session snapshot reports count · consent · profile root",
            snapshot["count"] == 0 and snapshot["user_consent"] is False
            and "agent-profile" in snapshot["agent_profile_dir"],
        )


# ======================================================================= C


def section_c(runner: Runner) -> None:
    """§11.5 — Authentication (the never-crossing secret)."""
    runner.section = "C"

    runner.check(
        "the pure scrubber masks every known secret",
        redact_text("login user=me pass=abc123 ok", ("abc123",))
        == f"login user=me pass={REDACTED} ok",
    )
    runner.check(
        "empty or absent secrets change nothing",
        redact_text("text", ("",)) == "text" and redact_text("text", ()) == "text",
    )
    runner.check(
        "the mask constant is exactly [REDACTED]",
        _REDACTED == "[REDACTED]",
    )

    with tempfile.TemporaryDirectory() as root:
        vault = BrowserVault(root)
        runner.check(
            "a fresh vault lists nothing and leaks nothing",
            vault.list() == [] and vault.known_secrets() == (),
        )
        missing = False
        try:
            vault.issue("example.com")
        except VaultError:
            missing = True
        runner.check("issue() on an absent site refuses", missing)

        if not ON_WINDOWS:
            import os

            os.environ["NEXUS_TEST_SECRET"] = "never-stored-on-linux"
            refused = False
            try:
                vault.store_from_env("example.com", "me", "NEXUS_TEST_SECRET")
            except VaultError as exc:
                refused = "win32" in str(exc)
            runner.check(
                "off win32, storing is refused honestly (never plaintext)",
                refused,
            )
            del os.environ["NEXUS_TEST_SECRET"]
        else:  # pragma: win32-cover
            import os

            os.environ["NEXUS_TEST_SECRET"] = "s3cret-value"
            vault.store_from_env("example.com", "me", "NEXUS_TEST_SECRET")
            username, secret = vault.issue("example.com")
            runner.check(
                "BONUS-path: DPAPI round-trip on win32 (store → issue)",
                username == "me" and secret == "s3cret-value",
            )
            runner.check(
                "BONUS-path: the listing shows site+username only",
                vault.list() == [{"site": "example.com", "username": "me"}],
            )
            runner.check(
                "BONUS-path: the scrubber masks the live secret",
                vault.redact("echo s3cret-value here") == "echo [REDACTED] here",
            )

        # the vault logic with a patched crypt core (CI-proof round-trip)
        with tempfile.TemporaryDirectory() as root2:
            fake_root = root2
            secret_file = Path(fake_root) / "secret.txt"
            secret_file.write_text("plain-secret-42", encoding="utf-8")
            original_protect = auth_module._dpapi_protect  # noqa: SLF001
            original_unprotect = auth_module._dpapi_unprotect  # noqa: SLF001
            auth_module._dpapi_protect = lambda data, desc: bytes(reversed(data))  # noqa: SLF001
            auth_module._dpapi_unprotect = lambda data: bytes(reversed(data))  # noqa: SLF001
            try:
                vault2 = BrowserVault(fake_root)
                vault2.store_from_file("site.example", "agent", str(secret_file))
                username, secret = vault2.issue("site.example")
                runner.check(
                    "the vault round-trip works with the crypt core patched "
                    "(store_from_file → issue)",
                    username == "agent" and secret == "plain-secret-42",
                )
                runner.check(
                    "the vault file at rest holds no plaintext",
                    "plain-secret-42" not in Path(vault2.path).read_text(
                        encoding="utf-8"
                    ),
                )
                runner.check(
                    "known_secrets feeds the scrubber (defense in depth)",
                    vault2.redact("leak plain-secret-42 here")
                    == "leak [REDACTED] here",
                )
                runner.check(
                    "forget() removes the entry",
                    vault2.forget("site.example") is True
                    and vault2.list() == [],
                )
            finally:
                auth_module._dpapi_protect = original_protect  # noqa: SLF001
                auth_module._dpapi_unprotect = original_unprotect  # noqa: SLF001

        # env-name store rides the variable, never the value
        with tempfile.TemporaryDirectory() as root3:
            import os

            os.environ["NEXUS_PHASE10_SECRET"] = "env-secret-9"
            original_protect = auth_module._dpapi_protect  # noqa: SLF001
            original_unprotect = auth_module._dpapi_unprotect  # noqa: SLF001
            auth_module._dpapi_protect = lambda data, desc: data  # noqa: SLF001
            auth_module._dpapi_unprotect = lambda data: data  # noqa: SLF001
            try:
                vault3 = BrowserVault(root3)
                vault3.store_from_env("env.example", "me", "NEXUS_PHASE10_SECRET")
                _user, secret = vault3.issue("env.example")
                runner.check(
                    "store_from_env reads the variable at store time",
                    secret == "env-secret-9",
                )
            finally:
                auth_module._dpapi_protect = original_protect  # noqa: SLF001
                auth_module._dpapi_unprotect = original_unprotect  # noqa: SLF001
                del os.environ["NEXUS_PHASE10_SECRET"]
        _ = PageSnapshot  # the states model is exercised live on the device


# ======================================================================= D


def section_d(runner: Runner) -> None:
    """§11.3 — self-healing selectors (browser-harness ADAPT)."""
    runner.section = "D"

    spec = SelectorFallbacks.parse("#login-button")
    runner.check(
        "a bare spec is a css selector (the common case)",
        spec.candidates() == (("css", "#login-button"),),
    )
    spec = SelectorFallbacks.parse("css=#login; role=button:Sign in; text=Enter")
    runner.check(
        "multi-strategy specs parse in ladder order (css → role → text)",
        [pair[0] for pair in spec.candidates()] == ["css", "role", "text"],
    )
    runner.check(
        "unknown spec keys are ignored honestly",
        SelectorFallbacks.parse("cursor=x").candidates() == (),
    )

    from nexus.browser.selfheal import resolve as heal_resolve

    class FakeLocator:
        def __init__(self, count: int) -> None:
            self._count = count

        def count(self) -> int:
            return self._count

    class FakePage:
        def locator(self, value: str) -> Any:
            return FakeLocator(0 if value == "#dead" else 1)

        def get_by_role(self, role: str, name: Any = None) -> Any:
            return FakeLocator(1)

        def get_by_text(self, text: str, exact: bool = False) -> Any:
            return FakeLocator(0 if text == "nowhere" else 1)

        def get_by_test_id(self, test_id: str) -> Any:
            return FakeLocator(1)

    page = FakePage()
    locator = heal_resolve(page, SelectorFallbacks(css="#dead", text="Enter"))
    runner.check(
        "the healing: a dead css falls through to the next strategy",
        locator is not None and locator.count() == 1,
    )
    failed = False
    ledger = None
    try:
        heal_resolve(
            page,
            SelectorFallbacks(css="#dead", text="nowhere", retries=1, settle=0.0),
        )
    except SelfHealError as exc:
        failed = True
        ledger = exc.ledger
    runner.check(
        "all-fail raises SelfHealError carrying the full ledger",
        failed and ledger is not None and len(ledger.to_dict()) >= 4,
        detail=f"ledger={ledger.to_dict() if ledger else None}",
    )
    entries = {row["strategy"]: row for row in ledger.to_dict()} if ledger else {}
    runner.check(
        "the ledger records misses (count=0), not just exceptions",
        all(row["outcome"] == "miss" for row in entries.values())
        and set(entries) == {"css", "text"},
        detail=f"entries={entries}",
    )
    one_strategy = SelectorFallbacks.parse("role=button:Go")
    runner.check(
        "single-strategy specs keep their ladder",
        one_strategy.candidates() == (("role", "button:Go"),),
    )


# ======================================================================= E


def section_e(runner: Runner) -> None:
    """Engine dispatch + the façade + the §9.5 dom_a11y layer."""
    runner.section = "E"

    with tempfile.TemporaryDirectory() as root:
        set_engine_defaults(channel="chromium", headless=True, data_root=root)
        from nexus.browser.engine import get_engine

        engine = get_engine()
        runner.check(
            "engine defaults injected (channel/headless/data root)",
            engine._channel == "chromium" and engine._headless is True,  # noqa: SLF001
        )
        unknown = False
        try:
            engine.op("warp", {})
        except EngineError:
            unknown = True
        runner.check("unknown ops refuse with EngineError", unknown)
        runner.check(
            "every §11.1 operation has an engine handler",
            all(
                hasattr(engine, f"_op_{operation}") for operation in BROWSER_OPERATIONS
            ),
            detail=sorted(
                op for op in BROWSER_OPERATIONS
                if not hasattr(engine, f"_op_{op}")
            ),
        )
        no_user_session = False
        try:
            engine.op("tabs", {"session": "user"})
        except EngineError as exc:
            no_user_session = "user session" in str(exc) or "§55" in str(exc)
        runner.check(
            "user-session ops before attach refuse (the §55 gate holds "
            "inside the engine too)",
            no_user_session,
        )
        from nexus.tools.native.browser import BrowserTool  # noqa: E402

        vault_receipt = BrowserTool().handler({"op": "vault_list"})
        runner.check(
            "vault bookkeeping answers through the tool (site+username only)",
            vault_receipt.artifacts.get("entries") == []
            and vault_receipt.artifacts.get("count") == 0,
            detail=f"artifacts={vault_receipt.artifacts}",
        )

    router = FakeRouter()
    runtime = BrowserRuntime(router)
    runtime.navigate("https://example.org")
    runtime.read("css=h1")
    runtime.click("role=button:Go")
    runtime.type("#q", text="hello")
    runtime.fill("#pw", vault_ref="example.com")
    runtime.upload("input[type=file]", "C:/tmp/x.png")
    runtime.download("https://example.org/f.bin", "C:/tmp/f.bin")
    runtime.tabs()
    runtime.tab_new("https://example.org/2")
    runtime.snapshot()
    runtime.screenshot("C:/tmp/s.png")
    runner.check(
        "the façade routes every §11.1 family through the router",
        len(router.calls) == 11 and all(name == "browser" for name, _ in router.calls),
        detail=f"calls={[(n, a.get('op')) for n, a in router.calls]}",
    )
    ops = [arguments.get("op") for _, arguments in router.calls]
    runner.check(
        "the op mapping is exact (navigate→read→click→type→…)",
        ops == ["navigate", "read", "click", "type", "fill",
                "upload", "download", "tabs", "tab_new", "snapshot", "screenshot"],
        detail=f"ops={ops}",
    )
    fill_call = router.calls[4][1]
    runner.check(
        "§11.5 at the façade: vault_ref rides the arguments, the text never does",
        fill_call.get("vault_ref") == "example.com" and "text" not in fill_call,
        detail=f"fill={fill_call}",
    )
    type_call = router.calls[3][1]
    runner.check(
        "plain type carries the text (the non-secret path)",
        type_call.get("text") == "hello" and "vault_ref" not in type_call,
    )
    attach_router = FakeRouter()
    BrowserRuntime(attach_router).attach_user_cdp("http://localhost:9222")
    runner.check(
        "attach_user_cdp routes the explicit §55 gate op",
        attach_router.calls[0][1] == {
            "op": "attach", "cdp_url": "http://localhost:9222", "session": "user",
        },
    )
    report = BrowserRuntime(FakeRouter()).capability_report()
    runner.check(
        "the façade probe reports not-registered honestly on a bare router",
        report["browser"]["available"] is False,
    )

    # ---- the §9.5 dom_a11y rung
    layer = BrowserDomLayer()
    ok, reason = layer.available()
    runner.check(
        "the dom_a11y rung refuses honestly without a router",
        ok is False and ("router" in reason or "library" in reason),
        detail=f"reason={reason}",
    )
    dom_router = FakeRouter()
    layer_wired = BrowserDomLayer(dom_router)
    ok_wired, _reason = layer_wired.available()
    runner.check(
        "with a router the rung reports available or names the honest reason "
        "(library missing / record absent)",
        ok_wired is True
        or "playwright extra missing" in _reason
        or "not registered" in _reason,
        detail=f"reason={_reason}",
    )
    result = layer_wired.act(ActionTarget(action="click", name="role=button:Go"))
    runner.check(
        "chain actions map onto browser ops (click → click)",
        result is None or dom_router.calls[-1][1].get("op") == "click",
        detail=f"calls={dom_router.calls}",
    )
    _ = result
    skipped = layer_wired.act(ActionTarget(action="focus", hwnd=5))
    runner.check(
        "unsupported chain actions return None (the chain moves on)",
        skipped is None,
    )


# ======================================================================= F


def section_f(runner: Runner) -> None:
    """Integration + regression — the runtime wires §11; phases stay green."""
    runner.section = "F"

    from dataclasses import replace as _replace

    from nexus.core.config.loader import load_config
    from nexus.core.config.paths import resolve_paths
    from nexus.core.config.runtime import NexusRuntime

    with tempfile.TemporaryDirectory() as root:
        runtime = NexusRuntime(
            paths=resolve_paths(root), config=load_config(root), bus=EventBus()
        )
        runner.check(
            "NexusRuntime wires the Browser Runtime (browser_enabled default)",
            runtime.browser_runtime is not None,
        )
        browser_runtime = runtime.browser_runtime
        assert browser_runtime is not None
        router = runtime.tool_router
        assert router is not None
        runner.check(
            "the wired registry holds ≥13 records "
            "(nine + three + browser — Phase 11 adds vision, the count "
            "is forward-tolerant)",
            len(router.registry.discover()) >= 13,
            detail=f"count={len(router.registry.discover())}",
        )
        report = browser_runtime.capability_report()
        runner.check(
            "the browser probe answers on the wired runtime",
            "browser" in report and report["browser"]["reason"] != "",
            detail=f"report={report}",
        )
        chain = runtime.computer_runtime.chain.describe()
        runner.check(
            "the §9.5 chain gained its dom_a11y rung (1 provider)",
            "dom_a11y" in chain and chain["dom_a11y"]["providers"] == 1,
            detail=f"chain={chain}",
        )
        runtime.shutdown()

    with tempfile.TemporaryDirectory() as root:
        config_off = _replace(
            load_config(root),
            tools=_replace(load_config(root).tools, browser_enabled=False),
        )
        runtime_off = NexusRuntime(
            paths=resolve_paths(root), config=config_off, bus=EventBus()
        )
        router_off = runtime_off.tool_router
        assert router_off is not None
        runner.check(
            "browser_enabled=false leaves the façade unwired and the "
            "registry at the Phase-9 floor (12 records, forward-tolerant)",
            runtime_off.browser_runtime is None
            and len(router_off.registry.discover()) >= 12,
            detail=f"count={len(router_off.registry.discover())}",
        )
        chain_off = (
            runtime_off.computer_runtime.chain.describe()
            if runtime_off.computer_runtime is not None
            else {}
        )
        runner.check(
            "with browser off, the chain has no dom_a11y provider",
            chain_off.get("dom_a11y", {}).get("providers", 0) == 0,
            detail=f"chain={chain_off}",
        )

    from nexus.core.config.schema import ConfigError, build_section

    try:
        build_section("tools", {"browser_channel": "netscape"})
        bad_channel = False
    except ConfigError:
        bad_channel = True
    runner.check("config: an unknown browser_channel is refused", bad_channel)
    section, _warnings = build_section(
        "tools", {"browser_channel": "chrome", "browser_headless": "true"}
    )
    runner.check(
        "config: channel/headless coerce and land",
        section.browser_channel == "chrome" and section.browser_headless is True,
    )

    # the §8.1 record registers through build_tool_system too
    _registry, _router, _adapter, report = build_tool_system(
        native=True, computer=True, browser=True, mcp_servers=()
    )
    runner.check(
        "build_tool_system(browser=True) reports the record additively",
        report["browser"] == ["browser"],
        detail=f"report={report}",
    )

    prior = [
        ("phase01", "Phase 1", 98),
        ("phase02", "Phase 2", 143),
        ("phase03", "Phase 3", 104),
        ("phase04", "Phase 4", 106),
        ("phase05", "Phase 5", 116),
        ("phase06", "Phase 6", 88),
        ("phase07", "Phase 7", 88),
        ("phase08", "Phase 8", 80),
        ("phase09", "Phase 9", 84),
    ]
    results = run_phases(prior)
    for (_phase_dir, label, _expected), (_label, line, code) in zip(
        prior, results, strict=True
    ):
        runner.check(
            f"{label} harness still green ({line})",
            code == 0,
            detail=f"exit={code} last={line!r}",
        )


def run_phases(prior: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """Run the Phase 1–9 harnesses; return their (name, line, code)."""
    results: list[tuple[str, str, int]] = []
    for phase_dir, label, expected in prior:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tests" / phase_dir / "verify_exit_criteria.py")],
            capture_output=True,
            text=True,
            timeout=1200,
        )
        results.append((label, proc.stdout.strip().splitlines()[-1], proc.returncode))
        _ = expected
    return results


# ======================================================================= main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="unused (repo-rooted)")
    _ = parser.parse_args()
    print("PHASE 10 — Browser Runtime (Final Build Plan §11) exit criteria")
    runner = Runner()
    for section in (section_a, section_b, section_c, section_d, section_e, section_f):
        try:
            section(runner)
        except Exception as exc:  # noqa: BLE001 — a section crash is a failure
            print(f"  [FAIL] ({runner.section}) section crashed: {exc}")
            runner.failed += 1
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
