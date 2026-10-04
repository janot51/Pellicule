import asyncio
from pathlib import Path

import pytest

from pellicule.policy.service import PolicyService
from pellicule.session import SessionStore


def _register_pending_ask(lab_policy: PolicyService, call_id: str) -> dict:
    args = {"path": ".env"}
    ev = lab_policy.evaluate("planner", "read", args)
    assert ev.verdict == "ask"
    detail = lab_policy.policy_event_detail(ev, {"arguments": args})
    lab_policy.after_policy(call_id, "read", args, ev, detail, "planner")
    return detail


def test_ask_pending_then_approved(lab_policy: PolicyService) -> None:
    async def run() -> None:
        _register_pending_ask(lab_policy, "call_ask_1")
        assert "call_ask_1" in lab_policy.ask.pending

        update = lab_policy.on_tool_message(
            session_id="s",
            turn=2,
            model="m",
            tool_call_id="call_ask_1",
            content="file contents ok",
            case_dir=None,
        )
        assert update is not None
        assert update["detail"]["ask_state"] == "approved"
        assert update["detail"]["ask_transition"] is True
        assert "call_ask_1" not in lab_policy.ask.pending

    asyncio.run(run())


def test_ask_pending_then_rejected_triggers_retry(lab_policy: PolicyService) -> None:
    async def run() -> None:
        _register_pending_ask(lab_policy, "call_ask_2")

        update = lab_policy.on_tool_message(
            session_id="s",
            turn=2,
            model="m",
            tool_call_id="call_ask_2",
            content="User rejected the permission request",
            case_dir=None,
        )
        assert update is not None
        assert update["detail"]["ask_state"] == "rejected_by_user"

        retry = lab_policy.tool_request_retry_fields("read", {"path": ".env"})
        assert retry.get("retry_of") == "call_ask_2"

    asyncio.run(run())


def test_ask_emitted_via_emit_exec(tmp_path: Path, lab_policy: PolicyService, monkeypatch: pytest.MonkeyPatch) -> None:
    from pellicule.event_emit import emit_exec_from_request

    async def run() -> None:
        monkeypatch.chdir(tmp_path)
        store = SessionStore()
        events: list[dict] = []

        async def record(ev: dict) -> None:
            store.append_event(ev)
            events.append(ev)

        _register_pending_ask(lab_policy, "c1")

        await emit_exec_from_request(
            store,
            record,
            "mock/m",
            [{"role": "tool", "tool_call_id": "c1", "content": "ok"}],
            policy=lab_policy,
        )
        policy_updates = [e for e in events if e["layer"] == "policy" and e["detail"].get("ask_transition")]
        assert len(policy_updates) == 1
        assert policy_updates[0]["detail"]["ask_state"] == "approved"

    asyncio.run(run())


def test_builtin_env_triggers_ask(lab_policy: PolicyService) -> None:
    ev = lab_policy.evaluate("planner", "read", {"path": ".env"})
    assert ev.verdict == "ask"
    assert ev.ask_state == "pending"
    assert ev.builtin_rule is True
