from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FlatRule:
    tool: str
    pattern: str
    action: str
    source: str
    order: int

    def label(self) -> str:
        if self.pattern == "*":
            return f"{self.tool}: {self.action}"
        return f"{self.tool}: {self.action} {self.pattern}"


@dataclass
class AgentPermissions:
    name: str
    source: str
    rules: list[FlatRule] = field(default_factory=list)


@dataclass
class LoadedPolicyConfig:
    config_source: str
    dialect: str
    default_agent: str
    global_rules: list[FlatRule]
    agents: dict[str, AgentPermissions]
    mcp_tools: set[str]
    sources: list[str]
    agree_without_log: bool
    agent_bodies: dict[str, str] = field(default_factory=dict)
    slash_commands: set[str] = field(default_factory=set)

    def rules_for_mode(self, mode: str | None) -> list[FlatRule]:
        ordered: list[FlatRule] = list(self.global_rules)
        key = (mode or self.default_agent or "").strip()
        if key and key in self.agents:
            ordered.extend(self.agents[key].rules)
        elif self.default_agent and self.default_agent in self.agents:
            ordered.extend(self.agents[self.default_agent].rules)
        return sorted(ordered, key=lambda r: r.order)


@dataclass
class PolicyEvaluation:
    verdict: str
    ask_state: str | None
    matched_rule: str | None
    rule_source: str | None
    losers: list[str]
    tool: str
    path: str | None
    motif: str
    dialect: str
    config_source: str
    agree: bool
    hypothesis: str | None
    mcp_outside_table: bool
    builtin_rule: bool
