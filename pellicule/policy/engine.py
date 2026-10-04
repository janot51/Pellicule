from __future__ import annotations

from typing import Any

from pellicule.policy.builtin import BUILTIN_ENV_RULE, sensitive_env_ask
from pellicule.policy.matchers import (
    extract_tool_context,
    normalize_motif,
    rule_matches,
)
from pellicule.policy.models import FlatRule, LoadedPolicyConfig, PolicyEvaluation


def _format_losers(matched: list[FlatRule]) -> list[str]:
    if len(matched) <= 1:
        return []
    return [r.label() for r in matched[:-1]]


def evaluate_tool(
    config: LoadedPolicyConfig,
    *,
    mode: str | None,
    tool: str,
    arguments: Any,
) -> PolicyEvaluation:
    path, command, task_agent = extract_tool_context(tool, arguments)
    motif = normalize_motif(tool, arguments)
    dialect = config.dialect
    config_source = config.config_source
    agree = config.agree_without_log

    if tool in config.mcp_tools:
        return PolicyEvaluation(
            verdict="allow",
            ask_state=None,
            matched_rule="mcp: hors table de permissions agent",
            rule_source="config:mcp",
            losers=[],
            tool=tool,
            path=path,
            motif=motif,
            dialect=dialect,
            config_source=config_source,
            agree=agree,
            hypothesis=None,
            mcp_outside_table=True,
            builtin_rule=False,
        )

    rules = config.rules_for_mode(mode)
    tool_has_rules = any(r.tool == tool for r in rules)

    if sensitive_env_ask(tool, path):
        return PolicyEvaluation(
            verdict="ask",
            ask_state="pending",
            matched_rule=BUILTIN_ENV_RULE,
            rule_source="builtin",
            losers=[],
            tool=tool,
            path=path,
            motif=motif,
            dialect=dialect,
            config_source=config_source,
            agree=agree,
            hypothesis=None,
            mcp_outside_table=False,
            builtin_rule=True,
        )

    matched: list[FlatRule] = []
    for rule in rules:
        if rule_matches(rule.tool, rule.pattern, tool, path, command, task_agent):
            matched.append(rule)

    if not matched and not tool_has_rules:
        return PolicyEvaluation(
            verdict="allow",
            ask_state=None,
            matched_rule="hors table de permissions agent",
            rule_source=None,
            losers=[],
            tool=tool,
            path=path,
            motif=motif,
            dialect=dialect,
            config_source=config_source,
            agree=agree,
            hypothesis=None,
            mcp_outside_table=True,
            builtin_rule=False,
        )

    if not matched:
        hypothesis = "dialect_legacy" if dialect == "legacy" else None
        return PolicyEvaluation(
            verdict="allow",
            ask_state=None,
            matched_rule=None,
            rule_source=None,
            losers=[],
            tool=tool,
            path=path,
            motif=motif,
            dialect=dialect,
            config_source=config_source,
            agree=agree and hypothesis is None,
            hypothesis=hypothesis,
            mcp_outside_table=False,
            builtin_rule=False,
        )

    winner = matched[-1]
    verdict = winner.action
    ask_state = "pending" if verdict == "ask" else None
    return PolicyEvaluation(
        verdict=verdict,
        ask_state=ask_state,
        matched_rule=winner.label(),
        rule_source=winner.source,
        losers=_format_losers(matched),
        tool=tool,
        path=path,
        motif=motif,
        dialect=dialect,
        config_source=config_source,
        agree=agree,
        hypothesis=None,
        mcp_outside_table=False,
        builtin_rule=False,
    )
