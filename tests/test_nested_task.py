from __future__ import annotations

from pellicule.session import SessionStore


def test_spawn_child_session_sets_parent(monkeypatch, tmp_path):
    monkeypatch.setenv("PELLICULE_DATA", str(tmp_path))
    store = SessionStore()
    parent = store.ensure_session()
    child = store.spawn_child_session(parent)
    assert child != parent
    assert store.parent_session_id == parent
    store.pop_to_parent_session()
    assert store.session_id == parent
