from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pellicule.mcp_ingest import _diff_arguments, _link_tool_request, attach_case_write_link
from pellicule.mcp_tap import _read_frame, _write_frame
from pellicule.session import SessionStore


def test_frame_roundtrip(tmp_path: Path) -> None:
    import io

    payload = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
    buf = io.BytesIO()
    _write_frame(buf, payload)
    buf.seek(0)
    out = _read_frame(buf)
    assert out == payload


def test_mcp_tap_help() -> None:
    root = Path(__file__).resolve().parents[1]
    pellicule = root / ".venv" / "Scripts" / "pellicule.exe"
    proc = subprocess.run(
        [str(pellicule), "mcp-tap", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    combined = (proc.stdout + proc.stderr).lower()
    assert "ingest" in combined


def test_link_single_tool_request() -> None:
    events = [
        {
            "ts": "2026-01-01T12:00:00Z",
            "layer": "tool_request",
            "tool_call_id": "c1",
            "detail": {"tool": "agent-lab-doc_doc_inventory", "arguments": {"subdir": "sources"}},
        }
    ]
    tid, link = _link_tool_request(events, "doc_inventory", 1735732800.0)
    assert link == "ok"
    assert tid == "c1"


def test_link_ambiguous() -> None:
    events = [
        {
            "ts": "2026-01-01T12:00:00Z",
            "layer": "tool_request",
            "tool_call_id": "c1",
            "detail": {"tool": "agent-lab-doc_doc_inventory", "arguments": {}},
        },
        {
            "ts": "2026-01-01T12:00:01Z",
            "layer": "tool_request",
            "tool_call_id": "c2",
            "detail": {"tool": "agent-lab-doc_doc_inventory", "arguments": {}},
        },
    ]
    _tid, link = _link_tool_request(events, "doc_inventory", 1735732801.0)
    assert link == "ambiguous"


def test_argument_diff_added() -> None:
    diff = _diff_arguments({"subdir": "sources"}, {"subdir": "sources", "case_dir": "/x"})
    assert "case_dir" in diff["added"]
    assert diff["changed"] == []


def test_case_write_link_from_exec_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timezone

    monkeypatch.chdir(tmp_path)
    store = SessionStore()
    sid = store.ensure_session()
    path = tmp_path / "sessions" / sid / "events.jsonl"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    ev = {
        "ts": now,
        "layer": "exec",
        "tool_call_id": "exec-1",
        "detail": {"body": {"head": "wrote analysis/NOTES.md ok"}},
    }
    path.write_text(json.dumps(ev) + "\n", encoding="utf-8")
    detail: dict = {"path": "analysis/NOTES.md"}
    attach_case_write_link(store, detail)
    assert detail.get("linked_tool_call_id") == "exec-1"
    assert detail.get("link") == "ok"
