from __future__ import annotations

from pellicule import schema
from pellicule.replay import cumulative_tokens, list_sessions, load_session_events, session_case_dir
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


def test_session_case_dir_from_meta_and_events(monkeypatch, tmp_path):
    monkeypatch.setenv("PELLICULE_DATA", str(tmp_path))
    store = SessionStore()
    sid = store.ensure_session()
    store.set_case_dir("C:/affaires/demo")
    store.append_event(
        schema.build_event(
            session_id=sid,
            layer="llm",
            turn=1,
            model="m",
            summary="x",
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            detail={},
            case_dir="C:/affaires/from-event",
        )
    )
    assert session_case_dir(sid) == "C:/affaires/demo"
    meta_path = tmp_path / "sessions" / sid / "meta.json"
    meta_path.write_text('{"session_id": "' + sid + '"}', encoding="utf-8")
    assert session_case_dir(sid, load_session_events(sid)) == "C:/affaires/from-event"
