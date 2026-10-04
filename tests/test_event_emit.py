import asyncio
import json
from pathlib import Path

import pytest

from pellicule.event_emit import emit_exec_from_request, emit_llm_and_tool_requests
from pellicule.session import SessionStore
from pellicule.stream_relay import RequestTimer


def test_emit_exec_dedupes_tool_call_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        monkeypatch.chdir(tmp_path)
        store = SessionStore()
        events: list[dict] = []

        async def record(ev: dict) -> None:
            store.append_event(ev)
            events.append(ev)

        messages = [
            {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        ]
        await emit_exec_from_request(store, record, "mock/m", messages)
        await emit_exec_from_request(store, record, "mock/m", messages)
        assert len(events) == 1
        assert events[0]["layer"] == "exec"
        assert events[0]["tool_call_id"] == "call_1"
        assert "sha256" in events[0]["detail"]["body"]

    asyncio.run(run())


def test_emit_tool_requests_after_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        monkeypatch.chdir(tmp_path)
        store = SessionStore()
        events: list[dict] = []

        async def record(ev: dict) -> None:
            store.append_event(ev)
            events.append(ev)

        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_z",
                                "function": {"name": "write", "arguments": "{}"},
                            }
                        ]
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
        timer = RequestTimer()
        await emit_llm_and_tool_requests(
            store,
            record,
            timer,
            "mock/m",
            {"messages": []},
            stream=False,
            response_body=response,
            stream_fold={},
            error=None,
            latency_ms=5,
        )
        layers = [e["layer"] for e in events]
        assert layers == ["llm", "tool_request"]
        assert events[1]["detail"]["tool"] == "write"
        path = list((tmp_path / "sessions").glob("*/events.jsonl"))[0]
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["tool_call_id"] == "call_z"

    asyncio.run(run())
