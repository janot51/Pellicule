from __future__ import annotations

from pellicule import schema
from pellicule.replay import cumulative_tokens, list_sessions, load_session_events
from pellicule.session import SessionStore


def test_replay_reads_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("PELLICULE_DATA", str(tmp_path))
    store = SessionStore()
    sid = store.ensure_session()
    ev = schema.build_event(
        session_id=sid,
        layer="llm",
        turn=1,
        model="m",
        summary="completion",
        latency_ms=1,
        prompt_tokens=10,
        completion_tokens=5,
        detail={},
    )
    store.append_event(ev)
    sessions = list_sessions()
    assert len(sessions) == 1
    events = load_session_events(sid)
    assert len(events) == 1
    totals = cumulative_tokens(events)
    assert totals["total"] == 15
