from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from pellicule import schema
from pellicule.client_gate import ClientGate
from pellicule.event_emit import (
    emit_exec_from_request,
    emit_llm,
    emit_llm_and_tool_requests,
    resolve_mode_from_request,
)
from pellicule.kilo_tail import KiloTailCoordinator
from pellicule.hub import EventHub
from pellicule.keys import KeysError, provider_names
from pellicule.policy.service import PolicyService
from pellicule.session import SessionStore
from pellicule.watcher import WatcherCoordinator
from pellicule.stream_relay import RequestTimer, relay_sse, usage_tokens
from pellicule.upstream import (
    IMPLICIT_PROVIDER,
    ResolvedUpstream,
    chat_completions_url,
    models_url,
    resolve_model,
    resolve_provider,
    upstream_headers,
)

UPSTREAM_HEADER = "x-pellicule-upstream"
CLIENT_ID_HEADER = "x-pellicule-client"
MODE_HEADER = "x-pellicule-mode"
CASE_DIR_HEADER = "x-pellicule-case-dir"


def async_http_client(**kwargs: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(**kwargs)


def create_proxy_app(
    store: SessionStore,
    hub: EventHub,
    gate: ClientGate,
    policy: PolicyService | None = None,
    watcher: WatcherCoordinator | None = None,
    kilo_tail: KiloTailCoordinator | None = None,
) -> FastAPI:
    app = FastAPI(title="Pellicule proxy", docs_url=None, redoc_url=None)

    async def record_and_publish(event: dict[str, Any]) -> None:
        store.append_event(event)
        await hub.publish(event)

    bound_gate = gate

    async def gate_or_error(request: Request) -> JSONResponse | None:
        token = bound_gate.client_token(
            request.headers.get("authorization"),
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            request.headers.get(CLIENT_ID_HEADER),
        )
        decision = await bound_gate.try_acquire(token)
        if decision.allowed:
            return None
        sid = store.ensure_session()
        turn = store.next_turn()
        event = schema.build_event(
            session_id=sid,
            layer="llm",
            turn=turn,
            model=None,
            summary="client_rejected",
            latency_ms=0,
            prompt_tokens=None,
            completion_tokens=None,
            detail={"error": decision.reason},
        )
        await record_and_publish(event)
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "message": decision.reason,
                    "type": "pellicule_client_conflict",
                    "code": "client_conflict",
                }
            },
        )

    def rewrite_model_body(body: dict[str, Any], resolved: ResolvedUpstream) -> dict[str, Any]:
        out = dict(body)
        out["model"] = resolved.upstream_model
        return out

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        blocked = await gate_or_error(request)
        if blocked is not None:
            return blocked

        timer = RequestTimer()
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content={"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
            )
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"error": {"message": "Body must be object"}})

        model_name = str(body.get("model", ""))
        header_mode = request.headers.get(MODE_HEADER)
        mode_confidence: str | None = None
        if policy:
            active_mode, mode_confidence = await resolve_mode_from_request(
                store,
                record_and_publish,
                policy,
                body.get("messages"),
                header_mode,
                kilo_tail=kilo_tail,
            )
        else:
            active_mode = header_mode
        case_hdr = request.headers.get(CASE_DIR_HEADER)
        if watcher and case_hdr:
            await watcher.set_case_dir(Path(case_hdr))

        await emit_exec_from_request(
            store,
            record_and_publish,
            model_name or None,
            body.get("messages"),
            policy=policy,
            kilo_tail=kilo_tail,
        )

        try:
            resolved = resolve_model(model_name, request.headers.get(UPSTREAM_HEADER))
        except KeysError as exc:
            sid = store.ensure_session()
            turn = store.next_turn()
            event = schema.build_event(
                session_id=sid,
                layer="llm",
                turn=turn,
                model=model_name or None,
                summary="upstream_config_error",
                latency_ms=timer.elapsed_ms(),
                prompt_tokens=None,
                completion_tokens=None,
                detail={"error": str(exc)},
            )
            await record_and_publish(event)
            return JSONResponse(
                status_code=502,
                content={"error": {"message": str(exc), "type": "pellicule_config_error"}},
            )

        upstream_body = rewrite_model_body(body, resolved)
        url = chat_completions_url(resolved.credentials)
        headers = upstream_headers(resolved.credentials, json_body=True)
        stream = bool(body.get("stream"))
        active_mode = store.active_mode or (
            policy.resolve_mode(request.headers.get(MODE_HEADER)) if policy else None
        )
        mode_confidence = store.mode_confidence

        # Le client reste ouvert pendant tout le stream. Un `async with`
        # le fermerait au return, avant que Starlette ne lise le corps.
        client = async_http_client(timeout=httpx.Timeout(None))
        release_client = True
        try:
            if not stream:
                try:
                    resp = await client.post(url, json=upstream_body, headers=headers)
                except httpx.HTTPError as exc:
                    return await _llm_error_response(
                        store,
                        record_and_publish,
                        timer,
                        model_name,
                        body,
                        str(exc),
                        None,
                    )
                latency = timer.elapsed_ms()
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    data = None
                if resp.status_code >= 400:
                    msg = resp.text
                    if isinstance(data, dict) and "error" in data:
                        msg = json.dumps(data["error"], ensure_ascii=False)
                    await emit_llm(
                        store,
                        record_and_publish,
                        timer,
                        model_name,
                        body,
                        stream=False,
                        response_body=data if isinstance(data, dict) else None,
                        stream_fold={},
                        error=msg,
                        latency_ms=latency,
                        policy=policy,
                    )
                    return JSONResponse(status_code=resp.status_code, content=data or {"error": {"message": resp.text}})

                usage = data.get("usage") if isinstance(data, dict) else None
                pt, ct = usage_tokens(usage if isinstance(usage, dict) else None)
                await emit_llm_and_tool_requests(
                    store,
                    record_and_publish,
                    timer,
                    model_name,
                    body,
                    stream=False,
                    response_body=data if isinstance(data, dict) else None,
                    stream_fold={},
                    error=None,
                    latency_ms=latency,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    policy=policy,
                    mode=active_mode,
                    mode_confidence=mode_confidence,
                    kilo_tail=kilo_tail,
                )
                return JSONResponse(status_code=resp.status_code, content=data)

            try:
                req = client.build_request("POST", url, json=upstream_body, headers=headers)
                resp = await client.send(req, stream=True)
            except httpx.HTTPError as exc:
                return await _llm_error_response(
                    store,
                    record_and_publish,
                    timer,
                    model_name,
                    body,
                    str(exc),
                    None,
                )

            if resp.status_code >= 400:
                raw = await resp.aread()
                await resp.aclose()
                try:
                    err_data = json.loads(raw)
                except json.JSONDecodeError:
                    err_data = {"error": {"message": raw.decode("utf-8", errors="replace")}}
                await emit_llm(
                    store,
                    record_and_publish,
                    timer,
                    model_name,
                    body,
                    stream=True,
                    response_body=None,
                    stream_fold={},
                    error=json.dumps(err_data, ensure_ascii=False),
                    latency_ms=timer.elapsed_ms(),
                    policy=policy,
                )
                return JSONResponse(status_code=resp.status_code, content=err_data)

            release_client = False

            async def body_stream() -> Any:
                fold: dict[str, Any] = {}
                stream_error: str | None = None
                try:
                    try:
                        async for chunk, acc in relay_sse(resp.aiter_bytes()):
                            fold = acc
                            yield chunk
                    except httpx.HTTPError as exc:
                        stream_error = str(exc)
                        payload = json.dumps(
                            {
                                "error": {
                                    "message": stream_error,
                                    "type": "upstream_error",
                                }
                            },
                            ensure_ascii=False,
                        )
                        yield f"data: {payload}\n\n".encode()
                        yield b"data: [DONE]\n\n"
                finally:
                    await resp.aclose()
                    await client.aclose()
                    usage = fold.get("usage") if isinstance(fold.get("usage"), dict) else None
                    pt, ct = usage_tokens(usage)
                    await emit_llm_and_tool_requests(
                        store,
                        record_and_publish,
                        timer,
                        model_name,
                        body,
                        stream=True,
                        response_body=None,
                        stream_fold=fold,
                        error=stream_error,
                        latency_ms=timer.elapsed_ms(),
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        policy=policy,
                        mode=active_mode,
                        mode_confidence=mode_confidence,
                        kilo_tail=kilo_tail,
                    )

            return StreamingResponse(
                body_stream(),
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "text/event-stream"),
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        finally:
            if release_client:
                await client.aclose()

    @app.get("/v1/models")
    async def list_models(request: Request) -> Response:
        blocked = await gate_or_error(request)
        if blocked is not None:
            return blocked

        model_q = request.query_params.get("model", "")
        header_up = request.headers.get(UPSTREAM_HEADER)
        try:
            if model_q:
                resolved = resolve_model(model_q, header_up)
            elif header_up:
                resolved = resolve_provider(header_up)
            elif IMPLICIT_PROVIDER in provider_names():
                resolved = resolve_provider(IMPLICIT_PROVIDER)
            else:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "message": "Précisez ?model=<provider>/... ou l'en-tête X-Pellicule-Upstream.",
                            "type": "invalid_request_error",
                        }
                    },
                )
        except KeysError as exc:
            return JSONResponse(
                status_code=502,
                content={"error": {"message": str(exc), "type": "pellicule_config_error"}},
            )

        url = models_url(resolved.credentials)
        headers = upstream_headers(resolved.credentials)
        async with async_http_client(timeout=60.0) as client:
            try:
                resp = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                return JSONResponse(
                    status_code=502,
                    content={"error": {"message": str(exc), "type": "upstream_error"}},
                )
            data = resp.json() if resp.content else {}

        if not store.models_logged:
            store.mark_models_logged()
            _apply_context_window_from_models(store, data if isinstance(data, dict) else {})
            sid = store.ensure_session()
            turn = store.next_turn()
            event = schema.build_event(
                session_id=sid,
                layer="models",
                turn=turn,
                model=model_q or None,
                summary="models_list",
                latency_ms=None,
                prompt_tokens=None,
                completion_tokens=None,
                detail={"payload": data},
            )
            await record_and_publish(event)

        return JSONResponse(status_code=resp.status_code, content=data)

    return app


def _apply_context_window_from_models(store: SessionStore, data: dict[str, Any]) -> None:
    models = data.get("data")
    if not isinstance(models, list):
        return
    for item in models:
        if not isinstance(item, dict):
            continue
        for key in ("context_window", "max_context_tokens", "max_model_len"):
            val = item.get(key)
            if isinstance(val, int) and val > 0:
                store.set_context_window(val)
                return


async def _llm_error_response(
    store: SessionStore,
    record_and_publish,
    timer: RequestTimer,
    model_name: str,
    body: dict[str, Any],
    error: str,
    status: int | None,
) -> JSONResponse:
    await emit_llm(
        store,
        record_and_publish,
        timer,
        model_name,
        body,
        stream=bool(body.get("stream")),
        response_body=None,
        stream_fold={},
        error=error,
        latency_ms=timer.elapsed_ms(),
        policy=None,
    )
    code = status or 502
    return JSONResponse(
        status_code=code,
        content={"error": {"message": error, "type": "upstream_error"}},
    )
