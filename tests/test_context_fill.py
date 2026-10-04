from __future__ import annotations

import json

from pellicule.context_fill import compute_context_fill, utf8_byte_len
def test_context_fill_parts_no_overlap() -> None:
    agent = "AGENT_PROMPT_X"
    skill_body = "S" * 250
    system = f"{agent}\n{skill_body}\nreste"
    agent_end = len(agent)
    skill_start = agent_end + 1
    skill_end = skill_start + len(skill_body)
    blocks = [
        {"kind": "agent_prompt", "label": "agent", "start": 0, "end": agent_end},
        {"kind": "skill_body", "label": "skill", "start": skill_start, "end": skill_end},
        {"kind": "unknown", "label": "reste", "start": skill_end + 1, "end": len(system)},
    ]
    user_text = "bonjour"
    tool_text = "résultat outil"
    tools = [{"type": "function", "function": {"name": "read", "parameters": {}}}]
    request_body = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
            {"role": "tool", "content": tool_text},
        ],
        "tools": tools,
    }
    detail = {
        "prompt_blocks": blocks,
        "messages": [
            {"role": "user", "content": user_text, "truncated": False},
            {"role": "assistant", "content": "ok", "truncated": False},
        ],
    }
    cf = compute_context_fill(
        request_body,
        detail,
        window_tokens=131072,
        provider_prompt_tokens=0,
        provider_completion_tokens=2,
    )
    assert cf["unit"] == "bytes"
    assert cf["provider_prompt_tokens"] == 0
    assert cf["window_tokens"] == 131072
    parts = cf["parts"]
    assert parts["agent_prompt"] == utf8_byte_len(agent)
    assert parts["skill_body"] == len(skill_body)
    assert parts["conversation"] == utf8_byte_len(user_text) + utf8_byte_len("ok")
    assert parts["tool_results"] == utf8_byte_len(tool_text)
    assert parts["tool_schemas"] == len(json.dumps(tools, ensure_ascii=False).encode("utf-8"))
    assert cf["measured_bytes"] == sum(parts.values())
    assert "estimate_tokens" not in cf
    assert "percent" not in json.dumps(cf)


def test_context_fill_omits_tools_and_tool_messages() -> None:
    request_body = {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u"},
        ],
    }
    detail = {
        "prompt_blocks": [],
        "messages": [{"role": "user", "content": "u", "truncated": False}],
    }
    cf = compute_context_fill(
        request_body,
        detail,
        window_tokens=None,
        provider_prompt_tokens=None,
        provider_completion_tokens=None,
    )
    assert "tool_results" not in cf["parts"]
    assert "tool_schemas" not in cf["parts"]
    assert cf["window_tokens"] is None
    assert cf["provider_prompt_tokens"] is None


def test_context_fill_empty_tools_is_zero() -> None:
    request_body = {"messages": [], "tools": []}
    detail = {"messages": []}
    cf = compute_context_fill(request_body, detail, window_tokens=None, provider_prompt_tokens=0, provider_completion_tokens=None)
    assert cf["parts"]["tool_schemas"] == len(b"[]")
    assert cf["provider_prompt_tokens"] == 0
