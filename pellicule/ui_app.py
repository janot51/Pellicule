from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pellicule.hub import EventHub
from pellicule.layers import LAYER_META
from pellicule.replay import cumulative_tokens, list_sessions, load_session_events
from pellicule.settings import static_dir


def create_ui_app(hub: EventHub) -> FastAPI:
    app = FastAPI(title="Pellicule", docs_url=None, redoc_url=None)
    static_path = static_dir()
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_path / "index.html")

    @app.get("/api/layers")
    async def layers_api() -> dict[str, Any]:
        return LAYER_META

    @app.get("/sessions")
    async def sessions_list() -> dict[str, Any]:
        return {"sessions": list_sessions()}

    @app.get("/sessions/{session_id}")
    async def session_replay(session_id: str) -> dict[str, Any]:
        events = load_session_events(session_id)
        return {
            "session_id": session_id,
            "events": events,
            "tokens": cumulative_tokens(events),
        }

    @app.get("/events")
    async def events_sse() -> StreamingResponse:
        queue = await hub.subscribe()

        async def stream() -> Any:
            try:
                yield "data: {\"type\":\"connected\"}\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if event is None:
                        break
                    yield hub.sse_payload(event)
            finally:
                await hub.unsubscribe(queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
