from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from watchfiles import Change, awatch

from pellicule import schema
from pellicule.policy.matchers import normalize_path
from pellicule.policy.service import PolicyService
from pellicule.settings import WATCH_TICK_SECONDS, WatchIgnoreRules, watch_ignore_rules
from pellicule.session import SessionStore

RecordFn = Callable[[dict[str, Any]], Awaitable[None]]


def path_is_ignored(rel_posix: str, rules: WatchIgnoreRules) -> bool:
    parts = [p for p in rel_posix.split("/") if p]
    for part in parts[:-1]:
        if part in rules.dir_names:
            return True
    name = parts[-1] if parts else rel_posix
    for suffix in rules.suffixes:
        if suffix == "~" and name.endswith("~"):
            return True
        if suffix and name.endswith(suffix):
            return True
        if name == suffix.lstrip("."):
            return True
    return False


class CaseWatcher:
    def __init__(
        self,
        case_dir: Path,
        store: SessionStore,
        policy: PolicyService,
        record: RecordFn,
        *,
        rules: WatchIgnoreRules | None = None,
        tick_seconds: float | None = None,
    ) -> None:
        self.case_dir = case_dir.resolve()
        self.store = store
        self.policy = policy
        self.record = record
        self.rules = rules or watch_ignore_rules()
        self.tick_seconds = tick_seconds if tick_seconds is not None else WATCH_TICK_SECONDS
        self._ephemeral: dict[str, float] = {}

    def should_ignore(self, rel_path: str) -> bool:
        return path_is_ignored(normalize_path(rel_path), self.rules)

    def _edit_forbidden_by_policy(self, rel_path: str, mode: str | None) -> bool:
        active_mode = mode or self.policy.config.default_agent
        result = self.policy.evaluate(active_mode, "edit", {"path": rel_path})
        return result.verdict == "deny"

    async def emit_case_write(self, rel_path: str, change: str) -> None:
        if self.should_ignore(rel_path):
            return
        full = self.case_dir / rel_path
        if not full.is_file():
            return
        size = full.stat().st_size
        mode = self.store.active_mode
        forbidden = self._edit_forbidden_by_policy(rel_path, mode)
        detail: dict[str, Any] = {
            "path": rel_path,
            "action": change,
            "size_bytes": size,
        }
        if forbidden:
            detail["annotation"] = "écriture que la config interdisait"
            detail["policy_verdict"] = "deny"
        from pellicule.mcp_ingest import attach_case_write_link

        attach_case_write_link(self.store, detail)
        sid = self.store.ensure_session()
        turn = self.store.next_turn()
        summary = f"case_write {change} {rel_path}"
        event = schema.build_event(
            session_id=sid,
            layer="case_write",
            turn=turn,
            model=None,
            summary=summary,
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            detail=detail,
            case_dir=str(self.case_dir),
            mode=mode,
            mode_confidence="unknown" if mode else None,
        )
        await self.record(event)

    def _queue_ephemeral(self, rel_path: str) -> None:
        self._ephemeral[rel_path] = time.monotonic()

    async def flush_ephemeral(self) -> None:
        now = time.monotonic()
        expired = [
            p
            for p, started in self._ephemeral.items()
            if now - started >= self.tick_seconds
        ]
        for rel in expired:
            self._ephemeral.pop(rel, None)
            full = self.case_dir / rel
            if not full.exists():
                continue
            await self.emit_case_write(rel, "created")

    async def handle_change(self, change: Change, path: Path) -> None:
        try:
            rel = path.relative_to(self.case_dir).as_posix()
        except ValueError:
            return
        if self.should_ignore(rel):
            return
        if change == Change.deleted:
            self._ephemeral.pop(rel, None)
            return
        if not path.is_file():
            return
        action = "created" if change == Change.added else "modified"
        if action == "created":
            self._queue_ephemeral(rel)
            return
        await self.emit_case_write(rel, action)

    async def run(self) -> None:
        async for changes in awatch(self.case_dir, step=int(self.tick_seconds * 1000)):
            for change, path_str in changes:
                await self.handle_change(change, Path(path_str))
            await self.flush_ephemeral()

    async def handle_path_for_test(self, path: Path, action: str) -> None:
        """API de test sans boucle watchfiles."""
        rel = path.relative_to(self.case_dir).as_posix()
        if self.should_ignore(rel):
            return
        if not path.is_file():
            return
        await self.emit_case_write(rel, action)


class WatcherCoordinator:
    def __init__(
        self,
        store: SessionStore,
        policy: PolicyService,
        record: RecordFn,
    ) -> None:
        self.store = store
        self.policy = policy
        self.record = record
        self._task: asyncio.Task[None] | None = None
        self._watcher: CaseWatcher | None = None
        self._case_dir: Path | None = None

    @property
    def case_dir(self) -> Path | None:
        return self._case_dir

    async def set_case_dir(self, path: Path | None) -> None:
        if path is None:
            return
        resolved = path.expanduser().resolve()
        if not resolved.is_dir():
            return
        if self._case_dir == resolved and self._task is not None:
            return
        self._case_dir = resolved
        self.store.set_case_dir(str(resolved))
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._watcher = CaseWatcher(resolved, self.store, self.policy, self.record)
        self._task = asyncio.create_task(self._watcher.run())
