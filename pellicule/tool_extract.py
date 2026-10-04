from __future__ import annotations

import json
from typing import Any


def _empty_tool_slot() -> dict[str, Any]:
    return {
        "id": None,
        "type": "function",
        "function": {"name": "", "arguments": ""},
    }


def merge_tool_call_deltas(
    by_index: dict[int, dict[str, Any]],
    delta_tool_calls: Any,
) -> None:
    if not isinstance(delta_tool_calls, list):
        return
    for tc in delta_tool_calls:
        if not isinstance(tc, dict):
            continue
        idx = tc.get("index")
        if idx is None:
            idx = len(by_index)
        if not isinstance(idx, int):
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                idx = len(by_index)
        slot = by_index.setdefault(idx, _empty_tool_slot())
        if tc.get("id"):
            slot["id"] = tc["id"]
        if tc.get("type"):
            slot["type"] = tc["type"]
        fn = tc.get("function")
        if isinstance(fn, dict):
            inner = slot.setdefault("function", {"name": "", "arguments": ""})
            name_part = fn.get("name")
            if name_part:
                inner["name"] = (inner.get("name") or "") + str(name_part)
            args_part = fn.get("arguments")
            if args_part:
                inner["arguments"] = (inner.get("arguments") or "") + str(args_part)


def merge_stream_chunk(accumulated: dict[str, Any], chunk: dict[str, Any]) -> None:
    usage = chunk.get("usage")
    if isinstance(usage, dict):
        accumulated["usage"] = usage
    by_index: dict[int, dict[str, Any]] = accumulated.setdefault("tool_calls_by_index", {})
    for choice in chunk.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or {}
        if isinstance(delta, dict):
            merge_tool_call_deltas(by_index, delta.get("tool_calls"))
            for key in ("reasoning", "reasoning_content"):
                if key in delta and delta[key] is not None:
                    prev = accumulated.setdefault(key, "")
                    if isinstance(prev, str) and isinstance(delta[key], str):
                        accumulated[key] = prev + delta[key]
                    else:
                        accumulated[key] = delta[key]
        message = choice.get("message")
        if isinstance(message, dict):
            merge_tool_call_deltas(by_index, message.get("tool_calls"))


def tool_calls_from_fold(fold: dict[str, Any]) -> list[dict[str, Any]]:
    by_index = fold.get("tool_calls_by_index")
    if not isinstance(by_index, dict) or not by_index:
        return []
    ordered: list[dict[str, Any]] = []
    for key in sorted(by_index.keys(), key=lambda k: int(k) if str(k).isdigit() else k):
        tc = by_index[key]
        if isinstance(tc, dict) and tc.get("id"):
            ordered.append(tc)
    return ordered


def tool_calls_from_response(response_body: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not response_body:
        return []
    choices = response_body.get("choices")
    if not isinstance(choices, list) or not choices:
        return []
    first = choices[0]
    if not isinstance(first, dict):
        return []
    message = first.get("message")
    if not isinstance(message, dict):
        return []
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return [tc for tc in tool_calls if isinstance(tc, dict) and tc.get("id")]


def parse_arguments(raw: Any) -> Any:
    if not isinstance(raw, str) or not raw.strip():
        return raw if raw is not None else {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def tool_request_summary(tool_call: dict[str, Any]) -> str:
    fn = tool_call.get("function")
    name = ""
    if isinstance(fn, dict):
        name = str(fn.get("name") or "")
    call_id = tool_call.get("id") or "?"
    if name:
        return f"{name} ({call_id})"
    return f"tool ({call_id})"


def iter_tool_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    out: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "tool":
            out.append(msg)
    return out


def exec_summary(tool_message: dict[str, Any]) -> str:
    call_id = tool_message.get("tool_call_id") or "?"
    size = tool_message.get("content")
    if isinstance(size, str):
        nbytes = len(size.encode("utf-8"))
    elif size is not None:
        nbytes = len(str(size).encode("utf-8"))
    else:
        nbytes = 0
    return f"tool result {call_id} ({nbytes} o)"
