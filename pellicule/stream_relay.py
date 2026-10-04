from __future__ import annotations

import hashlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from pellicule.tool_extract import merge_stream_chunk

_MSG_CHAR_LIMIT = 2_000_000
_MSG_HEAD_CHARS = 2048


def _message_roles_summary(messages: list[Any] | None) -> list[dict[str, Any]]:
    if not messages:
        return []
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        size = None
        if isinstance(content, str):
            size = len(content)
        elif content is not None:
            size = len(json.dumps(content, ensure_ascii=False))
        out.append({"role": role, "content_bytes": size})
    return out


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _retain_message_content(text: str) -> dict[str, Any]:
    if len(text) <= _MSG_CHAR_LIMIT:
        return {"content": text, "truncated": False}
    head = text[:_MSG_HEAD_CHARS]
    data = text.encode("utf-8")
    return {
        "content": head,
        "truncated": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "head": head,
    }


def _messages_for_detail(
    request_body: dict[str, Any],
    response_body: dict[str, Any] | None,
    stream_fold: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in request_body.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("system", "user"):
            continue
        text = _content_to_text(msg.get("content"))
        entry: dict[str, Any] = {"role": role}
        entry.update(_retain_message_content(text))
        out.append(entry)

    assistant_text = ""
    if response_body:
        choices = response_body.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                assistant_text = _content_to_text(message.get("content"))
    elif stream_fold:
        assistant_text = _content_to_text(stream_fold.get("content") or stream_fold.get("text") or "")
    if assistant_text:
        entry = {"role": "assistant"}
        entry.update(_retain_message_content(assistant_text))
        out.append(entry)
    return out


def build_llm_detail(
    *,
    stream: bool,
    request_body: dict[str, Any],
    response_body: dict[str, Any] | None,
    stream_fold: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "stream": stream,
        "message_roles": _message_roles_summary(request_body.get("messages")),
        "messages": _messages_for_detail(request_body, response_body, stream_fold),
    }
    if error:
        detail["error"] = error
    if stream_fold:
        for key in ("reasoning", "reasoning_content"):
            if key in stream_fold:
                detail[key] = stream_fold[key]
    if response_body:
        detail["response_id"] = response_body.get("id")
        for key in ("reasoning", "reasoning_content"):
            if key in response_body and key not in detail:
                detail[key] = response_body[key]
        choices = response_body.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict):
                for key in ("reasoning", "reasoning_content"):
                    if key in msg and key not in detail:
                        detail[key] = msg[key]
    return detail


def usage_tokens(
    usage: dict[str, Any] | None,
) -> tuple[int | None, int | None]:
    if not usage:
        return None, None
    pt = usage.get("prompt_tokens")
    ct = usage.get("completion_tokens")
    return (
        int(pt) if isinstance(pt, (int, float)) else None,
        int(ct) if isinstance(ct, (int, float)) else None,
    )


async def relay_sse(
    upstream_lines: AsyncIterator[bytes],
) -> AsyncIterator[tuple[bytes, dict[str, Any]]]:
    """Relais chaque ligne upstream immédiatement ; accumule usage / reasoning pour l'événement."""
    fold: dict[str, Any] = {}
    async for raw in upstream_lines:
        yield raw, fold
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                merge_stream_chunk(fold, data)


class RequestTimer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)
