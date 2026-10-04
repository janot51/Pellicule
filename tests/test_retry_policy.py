from pellicule.policy.service import PolicyService


def test_retry_after_deny(lab_policy: PolicyService) -> None:
    args = {"path": "sources/x.pdf"}
    first = lab_policy.evaluate("planner", "read", args)
    assert first.verdict == "deny"
    detail = lab_policy.policy_event_detail(first, {"arguments": args})
    lab_policy.after_policy("call_deny_1", "read", args, first, detail, "planner")

    lab_policy.record_llm_completion_tokens(12)
    lab_policy.record_llm_completion_tokens(8)

    retry_fields = lab_policy.tool_request_retry_fields("read", args)
    assert retry_fields["retry_of"] == "call_deny_1"
    assert retry_fields["retry_index"] == 1
    assert retry_fields["retry_burned_completion_tokens"] == 20


def test_retry_after_ask_block(lab_policy: PolicyService) -> None:
    from pellicule.policy.matchers import normalize_motif

    args = {"path": "sources/x.pdf"}
    motif = normalize_motif("read", args)
    lab_policy.retry.register_block("call_ask", "read", motif, "ask")
    fields = lab_policy.tool_request_retry_fields("read", args)
    assert fields.get("retry_of") == "call_ask"
