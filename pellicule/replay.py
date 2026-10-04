from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pellicule.settings import sessions_dir


def list_sessions() -> list[dict[str, Any]]:
    root = sessions_dir()
    if not root.is_dir():
        return []
    sessions: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_dir():
            continue
        meta_path = path / "meta.json"
        meta: dict[str, Any] = {"session_id": path.name}
        if meta_path.is_file():
            try:
                loaded = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    meta.update(loaded)
            except (OSError, json.JSONDecodeError):
                pass
        events_path = path / "events.jsonl"
        meta["event_count"] = _count_lines(events_path)
        sessions.append(meta)
    return sessions


def load_session_events(session_id: str) -> list[dict[str, Any]]:
    path = sessions_dir() / session_id / "events.jsonl"
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def session_meta(session_id: str) -> dict[str, Any] | None:
    meta_path = sessions_dir() / session_id / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def cumulative_tokens(events: list[dict[str, Any]]) -> dict[str, int | None]:
    prompt = 0
    completion = 0
    has_any = False
    for ev in events:
        pt = ev.get("prompt_tokens")
        ct = ev.get("completion_tokens")
        if isinstance(pt, int):
            prompt += pt
            has_any = True
        if isinstance(ct, int):
            completion += ct
            has_any = True
    if not has_any:
        return {"prompt_tokens": None, "completion_tokens": None, "total": None}
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total": prompt + completion,
    }


def _count_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return sum(1 for line in path.open(encoding="utf-8") if line.strip())
    except OSError:
        return 0
