from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from pellicule import schema
from pellicule.retention import retain_text_body
from pellicule.session import SessionStore
from pellicule.settings import sessions_dir

RecordFn = Callable[[dict[str, Any]], Awaitable[None]]

_LINKED_MCP: set[str] = set()


def spoken_tool_name(name: str) -> str:
    idx = name.find("_")
    if idx > 0 and "-" in name[:idx]:
        return name[idx + 1 :]
    return name


def _parse_ts(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def load_recent_events(store: SessionStore, window_seconds: float = 120.0) -> list[dict[str, Any]]:
    sid = store.session_id
    if not sid:
        return []
    path = sessions_dir() / sid / "events.jsonl"
    if not path.is_file():
        return []
    now = datetime.now(timezone.utc).timestamp()
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if now - _parse_ts(ev.get("ts", "")) <= window_seconds:
            events.append(ev)
    return events


def _diff_arguments(req_args: dict[str, Any], mcp_args: dict[str, Any]) -> dict[str, Any]:
    req_keys = set(req_args.keys())
    mcp_keys = set(mcp_args.keys())
    return {
        "added": sorted(mcp_keys - req_keys),
        "removed": sorted(req_keys - mcp_keys),
        "changed": sorted(k for k in req_keys & mcp_keys if req_args[k] != mcp_args[k]),
    }


def _link_tool_request(
    events: list[dict[str, Any]],
    mcp_tool: str,
    now_ts: float,
    window_seconds: float = 120.0,
) -> tuple[str | None, str]:
    spoken = spoken_tool_name(mcp_tool)
    candidates: list[dict[str, Any]] = []
    for ev in reversed(events):
        if ev.get("layer") != "tool_request":
            continue
        if now_ts - _parse_ts(ev.get("ts", "")) > window_seconds:
            continue
        d = ev.get("detail") or {}
        tool = d.get("tool") or ""
        if spoken_tool_name(str(tool)) != spoken:
            continue
        tid = ev.get("tool_call_id")
        if tid and tid in _LINKED_MCP:
            continue
        candidates.append(ev)
    if len(candidates) == 0:
        return None, "none"
    if len(candidates) > 1:
        return None, "ambiguous"
    return str(candidates[0]["tool_call_id"]), "ok"


def attach_case_write_link(store: SessionStore, detail: dict[str, Any]) -> None:
    path = detail.get("path")
    if not path:
        detail["link"] = "none"
        return
    events = load_recent_events(store)
    hits: set[str] = set()
    for ev in events:
        if ev.get("layer") not in ("exec", "mcp"):
            continue
        d = ev.get("detail") or {}
        body = d.get("body") or {}
        hay = (body.get("head") or "") + (d.get("frame") or "")
        if path in hay and ev.get("tool_call_id"):
            hits.add(str(ev["tool_call_id"]))
    if len(hits) == 1:
        detail["linked_tool_call_id"] = next(iter(hits))
        detail["link"] = "ok"
    elif len(hits) == 0:
        detail["link"] = "none"
    else:
        detail["link"] = "ambiguous"


def _redact_api_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("apiKey", "api_key"):
                out[k] = "***"
            else:
                out[k] = _redact_api_keys(v)
        return out
    if isinstance(obj, list):
        return [_redact_api_keys(x) for x in obj]
    return obj


async def handle_ingest(store: SessionStore, record: RecordFn, body: dict[str, Any]) -> None:
    session_id = body.get("session_id")
    if session_id:
        store.adopt_session(str(session_id))
    else:
        store.ensure_session()

    direction = body.get("direction")
    frame_text = body.get("frame_text")
    parse_error = body.get("parse_error") is True
    payload: dict[str, Any] | None = None
    if frame_text and not parse_error:
        try:
            payload = json.loads(frame_text)
        except json.JSONDecodeError:
            parse_error = True

    detail: dict[str, Any] = {"direction": direction}
    if parse_error:
        detail["parse_error"] = True
        detail["size_bytes"] = body.get("size_bytes")
    elif payload is not None:
        payload = _redact_api_keys(payload)
        retained = retain_text_body(json.dumps(payload, ensure_ascii=False))
        detail["method"] = payload.get("method")
        detail["rpc_id"] = payload.get("id")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        if detail["method"] == "tools/call":
            detail["tool"] = params.get("name")
            detail["arguments"] = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if retained["size_bytes"] <= 2048:
            detail["frame"] = json.dumps(payload, ensure_ascii=False)
        else:
            detail["body"] = retained
        if detail.get("method") == "tools/list" and isinstance(params.get("tools"), list):
            detail["tools"] = params.get("tools")

    now_ts = datetime.now(timezone.utc).timestamp()
    events = load_recent_events(store)
    if detail.get("method") == "tools/call" and direction == "client" and detail.get("tool"):
        tid, link = _link_tool_request(events, str(detail["tool"]), now_ts)
        detail["link"] = link
        if link == "ok" and tid:
            detail["tool_call_id"] = tid
            _LINKED_MCP.add(tid)
            for ev in events:
                if ev.get("tool_call_id") == tid and ev.get("layer") == "tool_request":
                    req_args = (ev.get("detail") or {}).get("arguments") or {}
                    mcp_args = detail.get("arguments") or {}
                    raw_tool = (ev.get("detail") or {}).get("tool") or ""
                    diff = _diff_arguments(req_args, mcp_args)
                    if raw_tool != detail.get("tool"):
                        diff["tool_renamed"] = True
                    detail["argument_diff"] = diff
                    break

    sid = store.ensure_session()
    turn = store.next_turn()
    event = schema.build_event(
        session_id=sid,
        layer="mcp",
        turn=turn,
        model=None,
        summary=f"mcp {direction} {detail.get('method') or 'frame'}",
        latency_ms=None,
        prompt_tokens=None,
        completion_tokens=None,
        detail=detail,
        tool_call_id=detail.get("tool_call_id"),
        case_dir=store.case_dir,
        mode=store.active_mode,
        mode_confidence=store.mode_confidence,
        parent_session_id=store.parent_session_id,
    )
    await record(event)
