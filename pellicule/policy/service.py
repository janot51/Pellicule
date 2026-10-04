from __future__ import annotations

from typing import Any

from pellicule import schema
from pellicule.policy.ask_state import AskStateTracker
from pellicule.policy.engine import evaluate_tool
from pellicule.policy.matchers import normalize_motif
from pellicule.policy.models import LoadedPolicyConfig, PolicyEvaluation
from pellicule.policy.retry import RetryTracker


class PolicyService:
    def __init__(self, config: LoadedPolicyConfig) -> None:
        self.config = config
        self.retry = RetryTracker()
        self.ask = AskStateTracker()

    def resolve_mode(self, header_mode: str | None) -> str:
        if header_mode and header_mode.strip():
            return header_mode.strip()
        return self.config.default_agent

    def record_llm_completion_tokens(self, completion_tokens: int | None) -> None:
        self.retry.add_completion_tokens(completion_tokens)

    def tool_request_retry_fields(self, tool: str, arguments: Any) -> dict[str, Any]:
        motif = normalize_motif(tool, arguments)
        retry_of, retry_index, burned = self.retry.check_retry(tool, motif)
        if not retry_of:
            return {}
        return {
            "retry_of": retry_of,
            "retry_index": retry_index,
            "retry_burned_completion_tokens": burned,
        }

    def evaluate(self, mode: str, tool: str, arguments: Any) -> PolicyEvaluation:
        return evaluate_tool(self.config, mode=mode, tool=tool, arguments=arguments)

    def after_policy(
        self,
        tool_call_id: str,
        tool: str,
        arguments: Any,
        evaluation: PolicyEvaluation,
        policy_detail: dict[str, Any],
        mode: str,
    ) -> None:
        motif = evaluation.motif
        if evaluation.verdict == "deny":
            self.retry.register_block(tool_call_id, tool, motif, "deny")
        elif policy_detail.get("verdict") == "ask" and policy_detail.get("ask_state") == "pending":
            self.ask.register_pending(
                tool_call_id,
                tool,
                motif,
                mode,
                policy_detail,
            )

    def build_ask_update_event(
        self,
        *,
        session_id: str,
        turn: int,
        model: str | None,
        pending: Any,
        ask_state: str,
        case_dir: str | None,
    ) -> dict[str, Any]:
        detail = dict(pending.base_detail)
        detail["ask_state"] = ask_state
        detail["ask_transition"] = True
        summary = f"ask_{ask_state}"
        return schema.build_event(
            session_id=session_id,
            layer="policy",
            turn=turn,
            model=model,
            summary=summary,
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_id=pending.tool_call_id,
            detail=detail,
            mode=pending.mode,
            mode_confidence="unknown",
            case_dir=case_dir,
        )

    def on_tool_message(
        self,
        *,
        session_id: str,
        turn: int,
        model: str | None,
        tool_call_id: str,
        content: Any,
        case_dir: str | None,
    ) -> dict[str, Any] | None:
        resolved = self.ask.resolve(tool_call_id, content)
        if resolved is None:
            return None
        pending, ask_state = resolved
        if ask_state == "rejected_by_user":
            self.retry.register_block(
                pending.tool_call_id,
                pending.tool,
                pending.motif,
                "ask",
            )
        return self.build_ask_update_event(
            session_id=session_id,
            turn=turn,
            model=model,
            pending=pending,
            ask_state=ask_state,
            case_dir=case_dir,
        )

    def policy_summary(self, evaluation: PolicyEvaluation) -> str:
        parts = [evaluation.verdict, evaluation.tool]
        if evaluation.path:
            parts.append(evaluation.path)
        if evaluation.verdict == "ask" and evaluation.ask_state:
            parts.append(f"({evaluation.ask_state})")
        return " ".join(parts)

    def policy_event_detail(
        self,
        evaluation: PolicyEvaluation,
        tool_request_detail: dict[str, Any],
    ) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "tool": evaluation.tool,
            "path": evaluation.path,
            "verdict": evaluation.verdict,
            "ask_state": evaluation.ask_state,
            "matched_rule": evaluation.matched_rule,
            "rule_source": evaluation.rule_source,
            "config_source": evaluation.config_source,
            "dialect": evaluation.dialect,
            "precedence": "last-match-wins",
            "losers": evaluation.losers,
            "kilo_log": None,
            "agree": evaluation.agree,
            "hypothesis": evaluation.hypothesis,
            "mcp_outside_table": evaluation.mcp_outside_table,
            "builtin_rule": evaluation.builtin_rule,
            "arguments": tool_request_detail.get("arguments"),
            "retry_of": tool_request_detail.get("retry_of"),
            "retry_index": tool_request_detail.get("retry_index", 0),
            "retry_burned_completion_tokens": tool_request_detail.get(
                "retry_burned_completion_tokens"
            ),
        }
        if evaluation.mcp_outside_table:
            detail["annotation"] = "hors table de permissions agent"
        return detail
