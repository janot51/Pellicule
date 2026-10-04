from __future__ import annotations

import json
from typing import Any

_BLOCK_KIND_TO_PART = {
    "skill_body": "skill_body",
    "skill_catalogue": "skill_catalogue",
    "agent_prompt": "agent_prompt",
    "command_template": "command_template",
    "unknown": "system_unknown",
}


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def utf8_byte_len(content: Any) -> int:
    return len(_content_to_text(content).encode("utf-8"))


def _sum_prompt_block_parts(prompt_blocks: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for block in prompt_blocks:
        kind = block.get("kind")
        part_key = _BLOCK_KIND_TO_PART.get(kind)
        if not part_key:
            continue
        start = block.get("start")
        end = block.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            continue
        totals[part_key] = totals.get(part_key, 0) + (end - start)
    return totals


def _conversation_bytes(messages: list[dict[str, Any]] | None) -> int:
    if not messages:
        return 0
    total = 0
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        if msg.get("truncated") and isinstance(msg.get("size_bytes"), int):
            total += msg["size_bytes"]
        elif msg.get("content") is not None:
            total += utf8_byte_len(msg.get("content"))
    return total


def _tool_results_bytes(request_body: dict[str, Any]) -> int | None:
    raw_messages = request_body.get("messages")
    if not isinstance(raw_messages, list):
        return None
    tool_msgs = [m for m in raw_messages if isinstance(m, dict) and m.get("role") == "tool"]
    if not tool_msgs:
        return None
    return sum(utf8_byte_len(m.get("content")) for m in tool_msgs)


def _tool_schemas_bytes(request_body: dict[str, Any]) -> int | None:
    if "tools" not in request_body:
        return None
    tools = request_body.get("tools")
    if tools is None:
        return None
    return len(json.dumps(tools, ensure_ascii=False).encode("utf-8"))


def compute_context_fill(
    request_body: dict[str, Any],
    detail: dict[str, Any],
    *,
    window_tokens: int | None,
    provider_prompt_tokens: int | None,
    provider_completion_tokens: int | None,
) -> dict[str, Any]:
    parts: dict[str, int] = {}

    prompt_blocks = detail.get("prompt_blocks")
    if isinstance(prompt_blocks, list) and prompt_blocks:
        parts.update(_sum_prompt_block_parts(prompt_blocks))

    messages = detail.get("messages")
    if isinstance(messages, list):
        parts["conversation"] = _conversation_bytes(messages)

    tool_bytes = _tool_results_bytes(request_body)
    if tool_bytes is not None:
        parts["tool_results"] = tool_bytes

    schema_bytes = _tool_schemas_bytes(request_body)
    if schema_bytes is not None:
        parts["tool_schemas"] = schema_bytes

    measured = sum(parts.values()) if parts else 0

    out: dict[str, Any] = {
        "unit": "bytes",
        "parts": parts,
        "measured_bytes": measured,
        "window_tokens": window_tokens if isinstance(window_tokens, int) else None,
        "provider_prompt_tokens": (
            int(provider_prompt_tokens)
            if isinstance(provider_prompt_tokens, (int, float))
            else None
        ),
        "provider_completion_tokens": (
            int(provider_completion_tokens)
            if isinstance(provider_completion_tokens, (int, float))
            else None
        ),
    }
    return out
