from __future__ import annotations

from typing import Any, Awaitable, Callable

from pellicule import schema
from pellicule.policy.service import PolicyService
from pellicule.kilo_tail import KiloTailCoordinator
from pellicule.mode_detect import ModeDetection, detect_mode
from pellicule.retention import retain_text_body
from pellicule.session import SessionStore
from pellicule.stream_relay import RequestTimer, build_llm_detail, usage_tokens
from pellicule.tool_extract import (
    exec_summary,
    iter_tool_messages,
    parse_arguments,
    tool_calls_from_fold,
    tool_calls_from_response,
    tool_request_summary,
)

RecordFn = Callable[[dict[str, Any]], Awaitable[None]]


async def emit_mode_if_changed(
    store: SessionStore,
    record: RecordFn,
    detection: ModeDetection,
    *,
    previous_mode: str | None,
    previous_confidence: str | None,
) -> str | None:
    if not detection.mode:
        return previous_confidence
    changed = detection.mode != previous_mode or detection.confidence != previous_confidence
    store.set_active_mode(detection.mode, detection.confidence)
    if not changed and previous_mode:
        return detection.confidence
    sid = store.ensure_session()
    turn = store.next_turn()
    event = schema.build_event(
        session_id=sid,
        layer="mode",
        turn=turn,
        model=None,
        summary=f"mode {detection.mode}",
        latency_ms=None,
        prompt_tokens=None,
        completion_tokens=None,
        detail={
            "mode": detection.mode,
            "confidence": detection.confidence,
            "source": detection.source,
        },
        mode=detection.mode,
        mode_confidence=detection.confidence,
        case_dir=store.case_dir,
        parent_session_id=store.parent_session_id,
    )
    await record(event)
    return detection.confidence


async def resolve_mode_from_request(
    store: SessionStore,
    record: RecordFn,
    policy: PolicyService,
    messages: Any,
    header_mode: str | None,
    *,
    kilo_tail: KiloTailCoordinator | None = None,
) -> tuple[str | None, str | None]:
    if header_mode and header_mode.strip():
        mode = header_mode.strip()
        store.set_active_mode(mode, "exact")
        return mode, "exact"
    task_mode = None
    if kilo_tail:
        task_mode = kilo_tail.latest_task_mode()
    detection = detect_mode(policy.config, messages, task_mode=task_mode)
    prev_mode = store.active_mode
    prev_conf = store.mode_confidence
    await emit_mode_if_changed(
        store,
        record,
        detection,
        previous_mode=prev_mode,
        previous_confidence=prev_conf,
    )
    return detection.mode, store.mode_confidence or detection.confidence


async def emit_exec_from_request(
    store: SessionStore,
    record: RecordFn,
    model_name: str | None,
    messages: Any,
    *,
    policy: PolicyService | None = None,
    kilo_tail: KiloTailCoordinator | None = None,
) -> None:
    sid = store.ensure_session()
    case_dir = store.case_dir
    for msg in iter_tool_messages(messages):
        call_id = msg.get("tool_call_id")
        if not call_id or not isinstance(call_id, str):
            continue
        content = msg.get("content")
        if policy:
            turn = store.next_turn()
            update = policy.on_tool_message(
                session_id=sid,
                turn=turn,
                model=model_name,
                tool_call_id=call_id,
                content=content,
                case_dir=case_dir,
            )
            if update is not None:
                await record(update)
        parent = store.resolve_task_delegation(call_id)
        if parent:
            store.pop_to_parent_session()

        if not store.register_exec_tool_call(call_id):
            continue
        body = retain_text_body(content)
        turn = store.next_turn()
        event = schema.build_event(
            session_id=sid,
            layer="exec",
            turn=turn,
            model=model_name,
            summary=exec_summary(msg),
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_id=call_id,
            detail={
                "tool_call_id": call_id,
                "name": msg.get("name"),
                "body": body,
            },
            case_dir=case_dir,
            mode=store.active_mode,
            mode_confidence=store.mode_confidence or ("unknown" if store.active_mode else None),
            parent_session_id=store.parent_session_id,
        )
        await record(event)


async def emit_tool_requests(
    store: SessionStore,
    record: RecordFn,
    model_name: str | None,
    tool_calls: list[dict[str, Any]],
    *,
    policy: PolicyService | None = None,
    mode: str | None = None,
    mode_confidence: str | None = None,
    kilo_tail: KiloTailCoordinator | None = None,
) -> None:
    if not tool_calls:
        return
    sid = store.ensure_session()
    case_dir = store.case_dir
    active_mode = policy.resolve_mode(mode) if policy else (mode or None)
    if active_mode:
        store.set_active_mode(active_mode, mode_confidence)
    conf = mode_confidence or store.mode_confidence or ("unknown" if active_mode else None)

    for tc in tool_calls:
        call_id = tc.get("id")
        if not call_id:
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "")
        raw_args = fn.get("arguments")
        args = parse_arguments(raw_args)
        detail: dict[str, Any] = {
            "tool": name,
            "arguments": args,
        }
        if isinstance(raw_args, str) and args != raw_args:
            detail["arguments_raw"] = raw_args

        if policy:
            detail.update(policy.tool_request_retry_fields(name, args))

        turn = store.next_turn()
        event = schema.build_event(
            session_id=sid,
            layer="tool_request",
            turn=turn,
            model=model_name,
            summary=tool_request_summary(tc),
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_id=str(call_id),
            detail=detail,
            mode=active_mode,
            mode_confidence=conf,
            case_dir=case_dir,
            parent_session_id=store.parent_session_id,
        )
        await record(event)

        if not policy:
            continue

        evaluation = policy.evaluate(active_mode, name, args)
        policy_detail = policy.policy_event_detail(evaluation, detail)
        policy_turn = store.next_turn()
        policy_event = schema.build_event(
            session_id=sid,
            layer="policy",
            turn=policy_turn,
            model=model_name,
            summary=policy.policy_summary(evaluation),
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_id=str(call_id),
            detail=policy_detail,
            mode=active_mode,
            mode_confidence=conf,
            case_dir=case_dir,
            parent_session_id=store.parent_session_id,
        )
        await record(policy_event)
        if kilo_tail:
            kilo_tail.register_policy(
                tool_call_id=str(call_id),
                tool=name,
                evaluation=evaluation,
                policy_detail=policy_detail,
                mode=active_mode,
                mode_confidence=conf,
            )
        policy.after_policy(
            str(call_id),
            name,
            args,
            evaluation,
            policy_detail,
            active_mode,
        )
        if name == "task" and evaluation.verdict == "allow":
            parent_id = sid
            store.register_task_delegation(str(call_id), parent_id)
            store.spawn_child_session(parent_id)


async def emit_llm(
    store: SessionStore,
    record: RecordFn,
    timer: RequestTimer,
    model_name: str,
    request_body: dict[str, Any],
    *,
    stream: bool,
    response_body: dict[str, Any] | None,
    stream_fold: dict[str, Any],
    error: str | None,
    latency_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    policy: PolicyService | None = None,
) -> None:
    if policy and not error:
        policy.record_llm_completion_tokens(completion_tokens)
    sid = store.ensure_session()
    turn = store.next_turn()
    if prompt_tokens is None and completion_tokens is None and response_body:
        usage = response_body.get("usage")
        if isinstance(usage, dict):
            prompt_tokens, completion_tokens = usage_tokens(usage)
    summary = "completion_error" if error else ("completion_stream" if stream else "completion")
    detail = build_llm_detail(
        stream=stream,
        request_body=request_body,
        response_body=response_body,
        stream_fold=stream_fold,
        error=error,
    )
    event = schema.build_event(
        session_id=sid,
        layer="llm",
        turn=turn,
        model=model_name or None,
        summary=summary,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        detail=detail,
        case_dir=store.case_dir,
    )
    await record(event)


async def emit_llm_and_tool_requests(
    store: SessionStore,
    record: RecordFn,
    timer: RequestTimer,
    model_name: str,
    request_body: dict[str, Any],
    *,
    stream: bool,
    response_body: dict[str, Any] | None,
    stream_fold: dict[str, Any],
    error: str | None,
    latency_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    policy: PolicyService | None = None,
    mode: str | None = None,
    mode_confidence: str | None = None,
    kilo_tail: KiloTailCoordinator | None = None,
) -> None:
    await emit_llm(
        store,
        record,
        timer,
        model_name,
        request_body,
        stream=stream,
        response_body=response_body,
        stream_fold=stream_fold,
        error=error,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        policy=policy,
    )
    if error:
        return
    if stream:
        tool_calls = tool_calls_from_fold(stream_fold)
    else:
        tool_calls = tool_calls_from_response(response_body)
    await emit_tool_requests(
        store,
        record,
        model_name or None,
        tool_calls,
        policy=policy,
        mode=mode,
        mode_confidence=mode_confidence,
        kilo_tail=kilo_tail,
    )
