import asyncio
import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from pellicule.client_gate import ClientGate
from pellicule.hub import EventHub
from pellicule.proxy_app import create_proxy_app
from pellicule.session import SessionStore


def _fake_http_client(**kwargs):
    return _FakeAsyncClient(**kwargs)


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json=None, headers=None):
        return httpx.Response(
            200,
            json={
                "id": "x",
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    def build_request(self, method, url, json=None, headers=None):
        return httpx.Request(method, url, json=json, headers=headers)

    async def send(self, request, stream=False):
        return httpx.Response(200, json={"choices": []})

    async def get(self, url, headers=None):
        return httpx.Response(200, json={"data": []})


def test_missing_keys_emits_llm_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        monkeypatch.chdir(tmp_path)
        store = SessionStore()
        hub = EventHub()
        app = create_proxy_app(store, hub, ClientGate())
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "mock/x", "messages": []},
            )
        assert resp.status_code == 502
        sessions = list((tmp_path / "sessions").glob("*/events.jsonl"))
        assert len(sessions) == 1
        ev = json.loads(sessions[0].read_text(encoding="utf-8").strip())
        assert ev["layer"] == "llm"
        assert ev["summary"] == "upstream_config_error"

    asyncio.run(run())


def test_second_client_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pellicule.keys").write_text(
            "[mock]\nbase_url = http://example/v1\napi_key = k\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("pellicule.proxy_app.async_http_client", _fake_http_client)
        store = SessionStore()
        hub = EventHub()
        app = create_proxy_app(store, hub, ClientGate())
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/v1/chat/completions",
                headers={"X-Pellicule-Client": "test-a"},
                json={"model": "mock/x", "messages": []},
            )
            resp = await client.post(
                "/v1/chat/completions",
                headers={"X-Pellicule-Client": "test-b"},
                json={"model": "mock/x", "messages": []},
            )
        assert resp.status_code == 409

    asyncio.run(run())
