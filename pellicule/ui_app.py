from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pellicule.hub import EventHub
from pellicule.layers import LAYER_META
from pellicule.policy.jsonc import permission_object_for_tool
from pellicule.replay import cumulative_tokens, list_sessions, load_session_events, session_case_dir
from pellicule.settings import case_dir_from_env, static_dir

RecordFn = Callable[[dict[str, Any]], Awaitable[None]]


def create_ui_app(
    hub: EventHub,
    *,
    store: Any | None = None,
    record_and_publish: RecordFn | None = None,
) -> FastAPI:
    app = FastAPI(title="Pellicule", docs_url=None, redoc_url=None)
    static_path = static_dir()
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            static_path / "index.html",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/layers")
    async def layers_api() -> dict[str, Any]:
        return LAYER_META

    @app.get("/api/context")
    async def ui_context() -> dict[str, Any]:
        active: str | None = None
        if store is not None:
            active = store.case_dir
        env = case_dir_from_env()
        default = str(env) if env else None
        return {"case_dir": active or default}

    @app.get("/api/rule")
    async def rule_fragment(tool: str, rule_source: str, mode: str = "") -> JSONResponse:
        obj = permission_object_for_tool(rule_source, tool)
        if obj is None:
            raise HTTPException(status_code=404, detail="rule_not_found")
        return JSONResponse(obj)

    if store is not None and record_and_publish is not None:

        @app.post("/ingest")
        async def ingest(request: Request) -> JSONResponse:
            client = request.client
            if client is None or client.host not in ("127.0.0.1", "::1"):
                raise HTTPException(status_code=403, detail="forbidden")
            from pellicule.mcp_ingest import handle_ingest

            body = await request.json()
            await handle_ingest(store, record_and_publish, body)
            return JSONResponse({"ok": True})

    @app.get("/sessions")
    async def sessions_list() -> dict[str, Any]:
        return {"sessions": list_sessions()}

    @app.get("/sessions/{session_id}")
    async def session_replay(session_id: str) -> dict[str, Any]:
        events = load_session_events(session_id)
        return {
            "session_id": session_id,
            "case_dir": session_case_dir(session_id, events),
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
