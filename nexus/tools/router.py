"""Tool Router (Final Build Plan §8.2).

The verbatim pipeline::

    Agent
    → Tool discovery
    → Permission
    → Scope
    → Resource
    → Execute
    → Normalize result
    → Verify

:class:`ToolRouter` runs exactly this order for every call and records
a :class:`RouterTrace` entry per stage — the trace *proves* the order.
Stage semantics:

* **discovery** — registry lookup + honest capability check (an
  unavailable tool is a miss, not a crash);
* **permission** — one Phase-2 :class:`PolicyEngine` decision on the
  ``TOOL`` action (tool allow/block/confirm lists, autonomy OBSERVE
  mutation denial, SUGGEST escalation) **plus** the §8.1 risk gate
  (``risk > confirm_danger_above`` → human confirmation) and the
  network gate for network-dimension tools;
* **scope** — every ``scope_requirements.path_arguments`` value goes
  through the same engine as READ or WRITE (mutating operations);
  out-of-scope is escalated per §3.4 (never walled); network tools
  gate the host; confirmations fold into ONE request;
* **resource** — one Phase-3 concurrency slot for the duration of the
  execution (acquired → released in ``finally``; exhausted → honest
  refusal, never queueing);
* **execute** — the handler; ``ToolError``/any exception is an honest
  failure (data, not a crash). Handlers own their timeouts (the
  router measures elapsed, it does not kill mid-flight);
* **normalize** — handler result → :class:`ToolOutcome` (output,
  artifacts);
* **verify** — the §8.1 ``verification`` contract runs on the
  normalized result; a failed verification *flips* the outcome to a
  failure — a tool that claims success without evidence fails here.

Events (canonical §2.2 only): ``tool.called`` / ``tool.completed`` /
``tool.failed`` — published for direct ``route()`` calls; the
:class:`RoutedToolSink` (the §6.2 seam adapter) suppresses them
because the Agent Loop owns publication on that path — no duplicates.

Confirmation: gates that demand a human fold into one
:class:`ConfirmationRequest`; no hook installed, or a ``False``
verdict → the call fails honestly (the agent observes the refusal).

موجّه الأدوات — سبع مراحل حرفيًا، وكل استدعاء يترك أثرًا
مرتّبًا يثبت الترتيب، والتحقق يقلب النتيجة إن خلت من البرهان.

Stdlib only.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..agents.loop import ToolResult, ToolSink
from ..core.policy.engine import ActionType, PolicyAction, PolicyEngine
from ..core.policy.models import TaskPolicy
from ..events import EventBus, EventName
from ..resources.manager import ResourceManager
from .models import (
    ROUTER_STAGES,
    RouterTrace,
    ToolCallResult,
    ToolDefinition,
    ToolOutcome,
    ToolRisk,
    TraceEntry,
    VerificationReport,
    VerificationSpec,
    VerificationStrategy,
)
from .registry import RegisteredTool, ToolRegistry

logger = logging.getLogger("nexus.tools")

#: The §8.2 gate order (after the agent entry point).
PIPELINE: tuple[str, ...] = ROUTER_STAGES[1:]

ConfirmationHook = Callable[["ConfirmationRequest"], bool]


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    """One human-confirmation ask — all gate reasons folded together."""

    tool: str
    risk: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "risk": self.risk, "reasons": list(self.reasons)}


@dataclass(slots=True)
class _RouteState:
    """Mutable per-call build state (frozen into the outcome at exit)."""

    entries: list[TraceEntry] = field(default_factory=list)
    confirmations: list[str] = field(default_factory=list)
    denied: str = ""
    outcome: ToolOutcome | None = None
    verify_spec: VerificationSpec | None = None

    def add(self, stage: str, status: str, detail: str = "") -> None:
        self.entries.append(TraceEntry(stage=stage, status=status, detail=detail))


class ToolRouter:
    """The §8.2 router — one choke point, every tool call passes it.

    Injected engines are optional (unit tests may run bare); a missing
    engine is recorded honestly in the trace (``skip``) — never
    silently bypassed.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        policy_engine: PolicyEngine | None = None,
        resources: ResourceManager | None = None,
        bus: EventBus | None = None,
        confirm_danger_above: int = 2,
        confirmation_hook: ConfirmationHook | None = None,
        allow_network: bool = True,
    ) -> None:
        self._registry = registry
        self._policy_engine = policy_engine
        self._resources = resources
        self._bus = bus
        self._confirm_danger_above = confirm_danger_above
        self._confirmation_hook = confirmation_hook
        self._allow_network = allow_network

    # ------------------------------------------------------------- plumbing

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def available_names(self) -> tuple[str, ...]:
        """Discovery view for the §6.2 loop — capability-honest names."""
        return tuple(
            definition.name
            for definition in self._registry.discover(available_only=True)
        )

    # ------------------------------------------------------------- the route

    def route(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        task_id: str = "",
        agent_id: str = "",
        policy: TaskPolicy | None = None,
        workspace_id: str | None = None,
        publish_events: bool = True,
    ) -> ToolOutcome:
        """Run the seven-stage pipeline for one call."""
        started = time.monotonic()
        state = _RouteState()
        state.add("agent", "info", agent_id or task_id or "direct")
        if publish_events and self._bus is not None:
            self._bus.publish(
                EventName.TOOL_CALLED,
                payload={"agent_id": agent_id, "tool": name, "task_id": task_id},
                source="nexus.tools.router",
                task_id=task_id or None,
            )
        registered = self._discovery(name, arguments, state)
        if registered is not None and not state.denied:
            self._permission(registered, arguments, policy, state)
        if registered is not None and not state.denied:
            self._resolve_confirmation(name, registered, state)
        if registered is not None and not state.denied:
            self._scope(registered, arguments, policy, workspace_id, state)
        if registered is not None and not state.denied:
            self._resolve_confirmation(name, registered, state)
        if registered is not None and not state.denied:
            self._execute_and_normalize(
                name, registered, arguments, task_id, state
            )
        if registered is not None and not state.denied and state.outcome is not None:
            self._verify(registered, state)
        outcome = self._finalize(
            name, state, started, publish_events, task_id, agent_id
        )
        return outcome

    # -------------------------------------------------------- stage 1 discovery

    def _discovery(
        self, name: str, arguments: Mapping[str, Any], state: _RouteState
    ) -> RegisteredTool | None:
        registered = self._registry.get(name)
        if registered is None:
            state.add("discovery", "fail", f"unknown tool {name!r}")
            state.denied = f"unknown tool: {name!r}"
            return None
        capabilities = registered.capabilities()
        if not capabilities.available:
            state.add(
                "discovery",
                "fail",
                f"tool {name!r} unavailable: {capabilities.reason}",
            )
            state.denied = f"tool {name!r} unavailable on this platform: {capabilities.reason}"
            return registered
        state.add(
            "discovery",
            "pass",
            f"{registered.definition.id} v{registered.definition.version}",
        )
        return registered

    # -------------------------------------------------------- stage 2 permission

    def _permission(
        self,
        registered: RegisteredTool,
        arguments: Mapping[str, Any],
        policy: TaskPolicy | None,
        state: _RouteState,
    ) -> None:
        definition = registered.definition
        # The §8.1 risk gate — config-level, policy-independent: above
        # the threshold a human confirms, always.
        if definition.risk > self._confirm_danger_above:
            state.confirmations.append(
                f"risk {definition.risk} ({ToolRisk.label(definition.risk)}) "
                f"> threshold {self._confirm_danger_above}"
            )
        # Network-dimension tools respect the tools config gate.
        network = "network" in definition.scope_requirements.dimensions or any(
            tag.startswith("network.") for tag in definition.permissions
        )
        if network and not self._allow_network:
            state.add("permission", "fail", "network disabled by tools config")
            state.denied = "network disabled by tools.allow_network=false"
            return
        if policy is None or self._policy_engine is None:
            state.add("permission", "skip", "no policy engine/policy bound")
            return
        mutating = self._is_mutating(definition, arguments)
        decision = self._policy_engine.decide(
            PolicyAction(
                action_type=ActionType.TOOL,
                target=definition.name,
                workspace_id=None,
                detail="mutating" if mutating else "read",
            ),
            policy,
        )
        if not decision.allowed:
            state.add("permission", "fail", decision.reason)
            state.denied = f"permission denied: {decision.reason}"
            return
        if decision.requires_confirmation:
            state.confirmations.append(f"policy: {decision.reason}")
        # The task policy's offline network rule.
        if network and policy.network_policy.offline:
            state.add("permission", "fail", "network offline by policy")
            state.denied = "network offline by task policy"
            return
        state.add(
            "permission",
            "pass",
            f"autonomy={policy.autonomy_level.name} risk={definition.risk}",
        )

    # ---------------------------------------------------------- stage 3 scope

    def _scope(
        self,
        registered: RegisteredTool,
        arguments: Mapping[str, Any],
        policy: TaskPolicy | None,
        workspace_id: str | None,
        state: _RouteState,
    ) -> None:
        definition = registered.definition
        if policy is None or self._policy_engine is None:
            state.add("scope", "skip", "no policy engine/policy bound")
            return
        mutating = self._is_mutating(definition, arguments)
        requirements = definition.scope_requirements
        checked = 0
        for argument_name in requirements.path_arguments:
            raw = arguments.get(argument_name)
            if not isinstance(raw, str) or not raw.strip():
                continue
            action_type = ActionType.WRITE if mutating else ActionType.READ
            decision = self._policy_engine.decide(
                PolicyAction(
                    action_type=action_type,
                    target=raw,
                    workspace_id=workspace_id,
                    detail=definition.name,
                ),
                policy,
            )
            checked += 1
            if not decision.allowed:
                state.add("scope", "fail", f"{argument_name}: {decision.reason}")
                state.denied = (
                    f"scope denied for {argument_name}={raw!r}: {decision.reason}"
                )
                return
            if decision.requires_confirmation:
                state.confirmations.append(f"scope: {decision.reason}")
        # Network-dimension tools scope the destination host.
        network = "network" in requirements.dimensions
        if network:
            raw_host = arguments.get("host")
            if isinstance(raw_host, str) and raw_host.strip():
                host = raw_host
            elif definition.name == "github":
                host = "api.github.com"
            else:
                host = "*"
            decision = self._policy_engine.decide(
                PolicyAction(
                    action_type=ActionType.NETWORK,
                    target=host,
                    workspace_id=workspace_id,
                    detail=definition.name,
                ),
                policy,
            )
            checked += 1
            if not decision.allowed:
                state.add("scope", "fail", f"host {host}: {decision.reason}")
                state.denied = f"network denied for host {host!r}: {decision.reason}"
                return
            if decision.requires_confirmation:
                state.confirmations.append(f"network: {decision.reason}")
        detail = f"{checked} target(s), {'mutating' if mutating else 'read'}"
        state.add("scope", "pass" if checked else "skip", detail)

    # -------------------------------------------------------- confirmation fold

    def _resolve_confirmation(
        self, name: str, registered: RegisteredTool, state: _RouteState
    ) -> None:
        """Fold pending confirmations into ONE ask — before any execute."""
        if not state.confirmations:
            return
        request = ConfirmationRequest(
            tool=name,
            risk=registered.definition.risk,
            reasons=tuple(state.confirmations),
        )
        if self._confirmation_hook is None:
            state.add(
                "permission",
                "fail",
                f"confirmation required ({'; '.join(request.reasons)}) "
                "— no confirmation hook installed",
            )
            state.denied = (
                f"tool {name!r} requires human confirmation "
                f"({'; '.join(request.reasons)}) — no confirmation hook installed"
            )
            state.confirmations.clear()
            return
        verdict = self._confirmation_hook(request)
        state.confirmations.clear()
        if not verdict:
            state.add("permission", "fail", "denied by confirmation hook")
            state.denied = f"tool {name!r} denied by confirmation hook"
            return
        state.add("permission", "confirmed", "; ".join(request.reasons))

    # ------------------------------------------------ stage 4/5 resource+execute

    def _execute_and_normalize(
        self,
        name: str,
        registered: RegisteredTool,
        arguments: Mapping[str, Any],
        task_id: str,
        state: _RouteState,
    ) -> None:
        acquired = False
        if self._resources is not None:
            acquired = self._resources.acquire_concurrency()
            if not acquired:
                state.add("resource", "fail", "concurrency budget exhausted")
                state.denied = "resource gate: concurrency budget exhausted"
                return
            state.add("resource", "pass", "concurrency slot acquired")
        else:
            state.add("resource", "skip", "no resource manager bound")
        try:
            try:
                raw = registered.handler(dict(arguments))
            except Exception as exc:  # noqa: BLE001 — tool failure is data
                state.add("execute", "fail", f"{type(exc).__name__}: {exc}")
                state.outcome = ToolOutcome(
                    tool=name,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
                return
            if isinstance(raw, ToolCallResult):
                result = raw
            elif isinstance(raw, str):
                result = ToolCallResult(output=raw)
            else:
                result = ToolCallResult(output=str(raw))
            state.add("execute", "pass", f"{len(result.output)} chars")
            state.outcome = ToolOutcome(
                tool=name,
                ok=True,
                output=result.output,
                artifacts=dict(result.artifacts),
            )
            state.verify_spec = result.verify
            state.add("normalize", "pass", f"{len(result.artifacts)} artifact(s)")
        finally:
            if acquired and self._resources is not None:
                self._resources.release_concurrency()

    # ---------------------------------------------------------- stage 7 verify

    def _verify(self, registered: RegisteredTool, state: _RouteState) -> None:
        assert state.outcome is not None
        outcome = state.outcome
        if not outcome.ok:
            state.add("verify", "skip", "call failed — nothing to verify")
            return
        spec = state.verify_spec or registered.definition.verification
        report = self._run_verification(spec, outcome)
        if report.passed:
            state.add("verify", "pass", f"{spec.strategy}: {report.detail}")
            state.outcome = ToolOutcome(
                tool=outcome.tool,
                ok=True,
                output=outcome.output,
                error="",
                artifacts=outcome.artifacts,
                verification=report,
            )
            return
        state.add("verify", "fail", f"{spec.strategy}: {report.detail}")
        state.outcome = ToolOutcome(
            tool=outcome.tool,
            ok=False,
            output=outcome.output,
            error=f"verification failed ({spec.strategy}): {report.detail}",
            artifacts=outcome.artifacts,
            verification=report,
        )

    def _run_verification(
        self, spec: VerificationSpec, outcome: ToolOutcome
    ) -> VerificationReport:
        """Run the §8.1 verification contract on the normalized result."""
        strategy = spec.strategy
        artifacts = outcome.artifacts
        if strategy == VerificationStrategy.NONE:
            return VerificationReport(strategy, True, "not required")
        if strategy == VerificationStrategy.PATH_EXISTS:
            path = str(artifacts.get("path", ""))
            return VerificationReport(
                strategy, bool(path) and Path(path).exists(), f"path={path!r}"
            )
        if strategy == VerificationStrategy.PATH_SIZE:
            path = str(artifacts.get("path", ""))
            size = Path(path).stat().st_size if path and Path(path).exists() else -1
            return VerificationReport(strategy, size > 0, f"path={path!r} size={size}")
        if strategy == VerificationStrategy.OUTPUT_NONEMPTY:
            return VerificationReport(
                strategy, bool(outcome.output.strip()), "output empty"
            )
        if strategy == VerificationStrategy.EXIT_ZERO:
            code = artifacts.get("exit_code")
            return VerificationReport(
                strategy, code == 0, f"exit_code={code!r}"
            )
        if strategy == VerificationStrategy.TEXT_CONTAINS:
            needle = spec.argument
            return VerificationReport(
                strategy, needle in outcome.output, f"needle={needle!r}"
            )
        if strategy == VerificationStrategy.JSON_FIELD:
            value = artifacts.get(spec.argument)
            return VerificationReport(
                strategy, bool(value), f"artifact {spec.argument!r} truthy"
            )
        return VerificationReport(strategy, False, f"unknown strategy {strategy!r}")

    # ---------------------------------------------------------------- helpers

    def _is_mutating(
        self, definition: ToolDefinition, arguments: Mapping[str, Any]
    ) -> bool:
        """A call mutates when its op is declared mutating — or the tool
        declares no read ops at all (terminal-style: every call acts)."""
        mutating = definition.scope_requirements.mutating_operations
        if not mutating:
            return True
        operation = str(arguments.get("op", ""))
        return operation in mutating

    def _finalize(
        self,
        name: str,
        state: _RouteState,
        started: float,
        publish_events: bool,
        task_id: str,
        agent_id: str,
    ) -> ToolOutcome:
        elapsed = int((time.monotonic() - started) * 1000)
        outcome = state.outcome or ToolOutcome(tool=name, ok=False, error=state.denied)
        # fold the denied reason / trace / verification into the final outcome
        if state.denied and not outcome.error:
            outcome = ToolOutcome(
                tool=name,
                ok=False,
                output=outcome.output,
                error=state.denied,
            )
        trace = RouterTrace(entries=tuple(state.entries))
        final = ToolOutcome(
            tool=name,
            ok=outcome.ok,
            output=outcome.output,
            error=outcome.error,
            artifacts=outcome.artifacts,
            verification=outcome.verification,
            trace=trace,
            elapsed_ms=elapsed,
        )
        if publish_events and self._bus is not None:
            event = EventName.TOOL_COMPLETED if final.ok else EventName.TOOL_FAILED
            payload: dict[str, Any] = {"agent_id": agent_id, "tool": name}
            if not final.ok:
                payload["error"] = final.error
            self._bus.publish(
                event,
                payload=payload,
                source="nexus.tools.router",
                task_id=task_id or None,
            )
        if not final.ok:
            logger.info("tool %s failed: %s", name, final.error)
        return final


class RoutedToolSink(ToolSink):
    """The §6.2 seam adapter — the loop dispatches through the router.

    The loop keeps owning ``tool.called`` / ``tool.completed`` /
    ``tool.failed`` publication (its §6.2 contract); this sink routes
    with ``publish_events=False`` so no event is duplicated. The
    verification note rides the output so the agent sees the proof.
    """

    def __init__(
        self,
        router: ToolRouter,
        *,
        policy: TaskPolicy | None = None,
        workspace_id: str | None = None,
        agent_id: str = "",
    ) -> None:
        self._router = router
        self._policy = policy
        self._workspace_id = workspace_id
        self._agent_id = agent_id

    @property
    def router(self) -> ToolRouter:
        return self._router

    def call(
        self, name: str, arguments: Mapping[str, Any], *, task_id: str
    ) -> ToolResult:
        outcome = self._router.route(
            name,
            arguments,
            task_id=task_id,
            agent_id=self._agent_id,
            policy=self._policy,
            workspace_id=self._workspace_id,
            publish_events=False,
        )
        output = outcome.output
        if outcome.ok and outcome.verification is not None:
            if outcome.verification.strategy != VerificationStrategy.NONE:
                output += f"\n[verify:{outcome.verification.strategy} ok]"
        return ToolResult(ok=outcome.ok, output=output, error=outcome.error)

    def available(self) -> tuple[str, ...]:
        return self._router.available_names()
