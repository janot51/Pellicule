from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pellicule.event_emit import emit_llm_and_tool_requests
from pellicule.prompt_blocks import compute_prompt_blocks
from pellicule.session import SessionStore
from pellicule.skills_index import SkillEntry, load_skills_from_paths, skill_body_newly_in_system
from pellicule.stream_relay import RequestTimer


def test_prompt_blocks_agent_and_skill_body(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills" / "demo-skill"
    skills_root.mkdir(parents=True)
    body = "X" * 250 + "\nCorps de skill pour le test."
    skills_root.joinpath("SKILL.md").write_text(
        f"---\nname: demo-skill\ndescription: Catalogue seulement\n---\n{body}",
        encoding="utf-8",
    )
    agent_prompt = "PROMPT_AGENT_UNIQUE pour ce test."
    system = f"{agent_prompt}\n{body}"
    config = {
        "agent": {"chef": {"prompt": agent_prompt}},
        "skills": {"paths": [str(tmp_path / "skills")]},
    }
    blocks = compute_prompt_blocks(system, config)
    kinds = {b["kind"] for b in blocks}
    assert "agent_prompt" in kinds
    assert "skill_body" in kinds


def test_skill_description_alone_does_not_load() -> None:
    desc_only = "description courte"
    body = "B" * 250
    assert not skill_body_newly_in_system(desc_only, f"intro {desc_only}", None)
    assert skill_body_newly_in_system(body, body, None)


def test_skill_why_null_without_tool_or_slash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pellicule.event_emit import _skill_why

    store = SessionStore()
    store.set_last_mode_source("default")
    why, _ = _skill_why("carte", store, {}, [])
    assert why is None


def test_compact_on_message_shrink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        monkeypatch.chdir(tmp_path)
        store = SessionStore()
        events: list[dict] = []

        async def record(ev: dict) -> None:
            store.append_event(ev)
            events.append(ev)

        timer = RequestTimer()
        msgs10 = [{"role": "user", "content": f"m{i}"} for i in range(10)]
        await emit_llm_and_tool_requests(
            store,
            record,
            timer,
            "mock",
            {"messages": msgs10},
            stream=False,
            response_body={"choices": [{"message": {"content": "ok"}}]},
            stream_fold={},
            error=None,
            latency_ms=1,
        )
        msgs4 = msgs10[:4]
        await emit_llm_and_tool_requests(
            store,
            record,
            timer,
            "mock",
            {"messages": msgs4},
            stream=False,
            response_body={"choices": [{"message": {"content": "ok2"}}]},
            stream_fold={},
            error=None,
            latency_ms=1,
        )
        compact = [e for e in events if e["layer"] == "compact"]
        assert len(compact) == 1
        assert compact[0]["detail"]["before_count"] == 10
        assert compact[0]["detail"]["after_count"] == 4
        assert compact[0]["detail"]["dropped_by_role"]["user"] == 6

    asyncio.run(run())


def test_task_without_brief_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
                                "id": "call_task",
                                "function": {
                                    "name": "task",
                                    "arguments": json.dumps({"agent": "ingestor"}),
                                },
                            }
                        ]
                    }
                }
            ]
        }
        timer = RequestTimer()
        await emit_llm_and_tool_requests(
            store,
            record,
            timer,
            "mock",
            {"messages": []},
            stream=False,
            response_body=response,
            stream_fold={},
            error=None,
            latency_ms=1,
        )
        tr = next(e for e in events if e["layer"] == "tool_request")
        assert tr["detail"]["delegation_agent"] == "ingestor"
        assert tr["detail"]["delegation_brief"] is None

    asyncio.run(run())
