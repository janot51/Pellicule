import asyncio
from pathlib import Path

import pytest

from pellicule.policy import PolicyService, load_policy_config
from pellicule.settings import WatchIgnoreRules
from pellicule.session import SessionStore
from pellicule.watcher import CaseWatcher


@pytest.fixture
def watcher_policy(monkeypatch: pytest.MonkeyPatch) -> PolicyService:
    lab = Path(__file__).resolve().parent / "fixtures" / "lab"
    monkeypatch.setenv("PELLICULE_MERGED_CONFIG", str(lab / "merged" / "kilo.jsonc"))
    monkeypatch.setenv("PELLICULE_MERGED_CONFIG", str(lab / "merged" / "kilo.jsonc"))
    cfg = load_policy_config()
    return PolicyService(cfg)


def test_ignore_tmp_file(tmp_path: Path, watcher_policy: PolicyService) -> None:
    async def run() -> None:
        store = SessionStore()
        events: list[dict] = []

        async def record(ev: dict) -> None:
            events.append(ev)

        rules = WatchIgnoreRules(suffixes=(".tmp",), dir_names=(".git",))
        watcher = CaseWatcher(tmp_path, store, watcher_policy, record, rules=rules)
        assert watcher.should_ignore("scratch.tmp")
        f = tmp_path / "scratch.tmp"
        f.write_text("x", encoding="utf-8")
        await watcher.handle_path_for_test(f, "modified")
        assert len(events) == 0

    asyncio.run(run())


def test_emits_case_write_for_normal_file(tmp_path: Path, watcher_policy: PolicyService) -> None:
    async def run() -> None:
        store = SessionStore()
        store.set_active_mode("planner")
        events: list[dict] = []

        async def record(ev: dict) -> None:
            events.append(ev)

        watcher = CaseWatcher(tmp_path, store, watcher_policy, record)
        f = tmp_path / "notes.txt"
        f.write_text("hello", encoding="utf-8")
        await watcher.handle_path_for_test(f, "modified")
        assert len(events) == 1
        assert events[0]["layer"] == "case_write"
        assert events[0]["detail"]["path"] == "notes.txt"
        assert events[0]["detail"]["action"] == "modified"

    asyncio.run(run())


def test_forbidden_write_annotation(tmp_path: Path, watcher_policy: PolicyService) -> None:
    async def run() -> None:
        store = SessionStore()
        store.set_active_mode("planner")
        events: list[dict] = []

        async def record(ev: dict) -> None:
            events.append(ev)

        watcher = CaseWatcher(tmp_path, store, watcher_policy, record)
        f = tmp_path / "analysis" / "secret.py"
        f.parent.mkdir(parents=True)
        f.write_text("print()", encoding="utf-8")
        await watcher.handle_path_for_test(f, "created")
        assert events[0]["detail"].get("annotation") == "écriture que la config interdisait"

    asyncio.run(run())
