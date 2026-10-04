from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def empty_event_fields() -> dict[str, Any]:
    return {
        "parent_session_id": None,
        "case_dir": None,
        "tool_call_id": None,
        "mode": None,
        "mode_confidence": None,
    }


def build_event(
    *,
    session_id: str,
    layer: str,
    turn: int,
    model: str | None,
    summary: str,
    latency_ms: int | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    detail: dict[str, Any] | None = None,
    tool_call_id: str | None = None,
    mode: str | None = None,
    mode_confidence: str | None = None,
    case_dir: str | None = None,
    parent_session_id: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "ts": utc_now_iso(),
        "session_id": session_id,
        "turn": turn,
        "layer": layer,
        "model": model,
        "summary": summary,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "detail": detail or {},
    }
    event.update(empty_event_fields())
    if tool_call_id is not None:
        event["tool_call_id"] = tool_call_id
    if mode is not None:
        event["mode"] = mode
    if mode_confidence is not None:
        event["mode_confidence"] = mode_confidence
    if case_dir is not None:
        event["case_dir"] = case_dir
    if parent_session_id is not None:
        event["parent_session_id"] = parent_session_id
    return event


def event_to_jsonl_line(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"
