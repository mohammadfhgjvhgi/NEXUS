"""Agent Registry (Final Build Plan §6.4).

The four verbs, verbatim from the plan (snake_case per codebase
convention — the mapping is one-to-one)::

    registerAgent      → AgentRegistry.register_agent
    unregisterAgent    → AgentRegistry.unregister_agent
    discoverAgents     → AgentRegistry.discover_agents
    getCapabilities    → AgentRegistry.get_capabilities

Semantics:

* the registry is the §0.5 NEXUS-owned single source of truth for who
  the agents are — no external framework registry is consulted;
* the pool is **never fixed**: register and unregister freely (same
  governing language as the §5.6 model pool — the list is open);
* ``discover_agents`` matches on capability and/or role — the §6.3
  Master Agent's delegation lookup;
* ``get_capabilities`` answers the §6.4 contract for one agent.

Persistence: atomic JSON (temp file + ``os.replace`` + ``fsync``) as
``agents.registry.json`` under ``NexusPaths.data`` — agents are
platform data, not model artifacts (``models`` dir) and not task
records (``tasks`` dir). The registry reloads on construction, so a
rebooted runtime finds its agents again (§2.6 continuation).

سجل الوكلاء — الأفعال الأربعة حرفيًا؛ القائمة مفتوحة أبدًا، والتخزين
ذرّي تحت data، ويُعاد تحميله عند الإقلاع.

Registry-semantics reference: autogen-core's register/subscribe
model (studied in vendor-staging, Repository-Integration Round 2,
MODE D — zero imports, patterns only).

Stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .agent import MASTER_AGENT_ID, Agent

logger = logging.getLogger("nexus.agents")

#: Registry file name (under ``NexusPaths.data``).
REGISTRY_FILE = "agents.registry.json"

#: Registry schema version.
REGISTRY_VERSION = 1


class AgentRegistryError(Exception):
    """Registry misuse (unknown agent, duplicate registration…)."""


class AgentRegistry:
    """The §6.4 Agent Registry — the four verbs + atomic persistence."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._agents: dict[str, Agent] = {}
        self._loaded_from_disk = False
        self._load()

    # ------------------------------------------------------------ verbs

    def register_agent(self, agent: Agent) -> Agent:
        """registerAgent — add (or refresh) one agent record."""
        if not isinstance(agent, Agent):
            raise AgentRegistryError(
                f"register_agent expects an Agent, got {type(agent)!r}"
            )
        existing = self._agents.get(agent.id)
        if existing is agent:  # same object — nothing to do
            return agent
        self._agents[agent.id] = agent
        self._save()
        logger.debug("agent %s registered (%s)", agent.id, agent.role)
        return agent

    def unregister_agent(self, agent_id: str) -> Agent:
        """unregisterAgent — remove one agent record (returns it)."""
        if agent_id == MASTER_AGENT_ID:
            raise AgentRegistryError(
                "the §6.3 Master Agent record cannot be unregistered"
            )
        agent = self._agents.pop(agent_id, None)
        if agent is None:
            raise AgentRegistryError(f"unknown agent id: {agent_id!r}")
        self._save()
        logger.debug("agent %s unregistered", agent_id)
        return agent

    def discover_agents(
        self,
        *,
        capability: str | None = None,
        role: str | None = None,
    ) -> tuple[Agent, ...]:
        """discoverAgents — agents matching capability and/or role.

        Matching is case-insensitive on role; capability matching is
        exact within each agent's capability tuple. With no filters the
        full roster (master included) is returned, in registration
        order; the master record only answers *filtered* lookups when
        its own role/capability matches.
        """
        results: list[Agent] = []
        for agent in self._agents.values():
            if agent.id == MASTER_AGENT_ID and (capability or role):
                # the master answers direct lookups only when explicitly asked
                if role and agent.role.lower() == role.lower():
                    results.append(agent)
                continue
            if role and agent.role.lower() != role.lower():
                continue
            if capability and capability not in agent.capabilities:
                continue
            results.append(agent)
        return tuple(results)

    def get_capabilities(self, agent_id: str) -> tuple[str, ...]:
        """getCapabilities — the capability tuple of one agent."""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentRegistryError(f"unknown agent id: {agent_id!r}")
        return agent.capabilities

    # ------------------------------------------------------------ extras

    def get(self, agent_id: str) -> Agent:
        """Fetch one agent record (raises on unknown ids)."""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentRegistryError(f"unknown agent id: {agent_id!r}")
        return agent

    def has(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def list_agents(self) -> tuple[Agent, ...]:
        """Full roster in registration order (master included)."""
        return tuple(self._agents.values())

    def __len__(self) -> int:
        return len(self._agents)

    # ------------------------------------------------------- persistence

    @property
    def registry_path(self) -> Path:
        return self._directory / REGISTRY_FILE

    def _load(self) -> None:
        path = self.registry_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("agent registry unreadable (%s) — starting empty", exc)
            return
        agents: dict[str, Agent] = {}
        for record in data.get("agents", []):
            try:
                agent = Agent.from_dict(record)
            except Exception as exc:  # noqa: BLE001 — one bad record must not kill the boot
                logger.warning("skipping malformed agent record: %s", exc)
                continue
            agents[agent.id] = agent
        self._agents = agents
        self._loaded_from_disk = True
        logger.debug("agent registry loaded (%d agents)", len(agents))

    def _save(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": REGISTRY_VERSION,
            "count": len(self._agents),
            "agents": [agent.to_dict() for agent in self._agents.values()],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._directory), prefix=".agents.registry.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.registry_path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    # -------------------------------------------------------- inspection

    def snapshot(self) -> Mapping[str, Any]:
        """Serializable snapshot (checkpoint / audit)."""
        return {
            "version": REGISTRY_VERSION,
            "count": len(self._agents),
            "agents": [agent.to_dict() for agent in self._agents.values()],
            "loaded_from_disk": self._loaded_from_disk,
        }

    def seed_master(self) -> Agent:
        """Idempotent §6.3 master-record seeding (first boot only)."""
        existing = self._agents.get(MASTER_AGENT_ID)
        if existing is not None:
            return existing
        master = Agent.master_record()
        self._agents[MASTER_AGENT_ID] = master
        self._save()
        logger.debug("master agent record seeded (%s)", MASTER_AGENT_ID)
        return master


def roster_ids(agents: Sequence[Agent]) -> tuple[str, ...]:
    """Helper: the ids of a sequence of agents (harness/report use)."""
    return tuple(agent.id for agent in agents)
