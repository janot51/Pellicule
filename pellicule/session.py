from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from pellicule import schema
from pellicule.settings import sessions_dir


class SessionStore:
    def __init__(self) -> None:
        self._session_id: str | None = None
        self._turn = 0
        self._models_logged = False
        self._dir: Path | None = None
        self._exec_tool_call_ids: set[str] = set()
        self._case_dir: str | None = None
        self._active_mode: str | None = None
        self._mode_confidence: str | None = None
        self._parent_session_id: str | None = None
        self._session_stack: list[str] = []
        self._context_window: int | None = None
        self._pending_task_parents: dict[str, str] = {}
        self._previous_system_text: str | None = None
        self._previous_message_fps: list[dict[str, str]] | None = None
        self._message_fps_session_id: str | None = None
        self._last_mode_source: str | None = None
        self._previous_turn_tool_args: list[dict[str, Any]] = []
        self._current_turn_tool_args: list[dict[str, Any]] = []
        self._notes_md_seen: bool = False
        self._llm_count: int = 0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def parent_session_id(self) -> str | None:
        return self._parent_session_id

    @property
    def models_logged(self) -> bool:
        return self._models_logged

    @property
    def mode_confidence(self) -> str | None:
        return self._mode_confidence

    @property
    def context_window(self) -> int | None:
        return self._context_window

    def set_context_window(self, value: int | None) -> None:
        if isinstance(value, int) and value > 0:
            self._context_window = value

    def mark_models_logged(self) -> None:
        self._models_logged = True

    def adopt_session(self, session_id: str) -> str:
        if self._session_id != session_id:
            self._detach_llm_message_context()
        self._session_id = session_id
        self._dir = sessions_dir() / session_id
        self._dir.mkdir(parents=True, exist_ok=True)
        return session_id

    def _detach_llm_message_context(self) -> None:
        """Oublie l'historique proxy du tour précédent (autre session ou nouvelle discussion)."""
        self._previous_message_fps = None
        self._message_fps_session_id = None
        self._previous_system_text = None
        self._notes_md_seen = False

    def ensure_session(self) -> str:
        if self._session_id is None:
            self._detach_llm_message_context()
            self._session_id = str(uuid.uuid4())
            self._dir = sessions_dir() / self._session_id
            self._dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, Any] = {
                "session_id": self._session_id,
                "started_at": schema.utc_now_iso(),
            }
            if self._parent_session_id:
                meta["parent_session_id"] = self._parent_session_id
            if self._case_dir:
                meta["case_dir"] = self._case_dir
            (self._dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._write_active_session()
        return self._session_id

    def _write_active_session(self) -> None:
        if not self._session_id:
            return
        path = sessions_dir().parent / "active_session.json"
        path.write_text(
            json.dumps({"session_id": self._session_id, "ts": schema.utc_now_iso()}, ensure_ascii=False),
            encoding="utf-8",
        )

    def spawn_child_session(self, parent_id: str) -> str:
        self._session_stack.append(parent_id)
        self._session_id = None
        self._dir = None
        self._turn = 0
        self._exec_tool_call_ids = set()
        self._parent_session_id = parent_id
        self._detach_llm_message_context()
        return self.ensure_session()

    def pop_to_parent_session(self) -> str | None:
        if not self._session_stack:
            self._parent_session_id = None
            return self._session_id
        parent = self._session_stack.pop()
        prev = self._session_id
        self._session_id = parent
        self._dir = sessions_dir() / parent
        if prev != parent:
            self._detach_llm_message_context()
        self._parent_session_id = None
        if self._session_stack:
            self._parent_session_id = self._session_stack[-1]
        return parent

    def register_task_delegation(self, tool_call_id: str, parent_id: str) -> None:
        self._pending_task_parents[tool_call_id] = parent_id

    def resolve_task_delegation(self, tool_call_id: str) -> str | None:
        return self._pending_task_parents.pop(tool_call_id, None)

    def next_turn(self) -> int:
        self._turn += 1
        return self._turn

    @property
    def active_mode(self) -> str | None:
        return self._active_mode

    def set_active_mode(self, mode: str | None, confidence: str | None = None) -> None:
        if mode:
            self._active_mode = mode
        if confidence:
            self._mode_confidence = confidence

    def set_case_dir(self, case_dir: str) -> None:
        self._case_dir = case_dir

    @property
    def case_dir(self) -> str | None:
        return self._case_dir

    def register_exec_tool_call(self, tool_call_id: str) -> bool:
        """Retourne True si cet id n'avait pas encore produit un événement exec."""
        if tool_call_id in self._exec_tool_call_ids:
            return False
        self._exec_tool_call_ids.add(tool_call_id)
        return True

    def append_event(self, event: dict[str, Any]) -> None:
        sid = self.ensure_session()
        if self._parent_session_id and not event.get("parent_session_id"):
            event["parent_session_id"] = self._parent_session_id
        if event.get("layer") == "case_write":
            detail = event.get("detail") or {}
            path_val = detail.get("path")
            if isinstance(path_val, str) and path_val.endswith("NOTES.md"):
                self._notes_md_seen = True
        assert self._dir is not None
        path = self._dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(schema.event_to_jsonl_line(event))

    @property
    def previous_system_text(self) -> str | None:
        return self._previous_system_text

    def set_previous_system_text(self, text: str | None) -> None:
        self._previous_system_text = text

    @property
    def previous_message_fps(self) -> list[dict[str, str]] | None:
        return self._previous_message_fps

    def previous_message_fps_for_compact(self) -> list[dict[str, str]]:
        if not self._session_id or self._message_fps_session_id != self._session_id:
            return []
        return list(self._previous_message_fps or [])

    def set_previous_message_fps(self, fps: list[dict[str, str]]) -> None:
        self._previous_message_fps = fps
        self._message_fps_session_id = self._session_id

    @property
    def last_mode_source(self) -> str | None:
        return self._last_mode_source

    def set_last_mode_source(self, source: str | None) -> None:
        self._last_mode_source = source

    @property
    def notes_md_seen(self) -> bool:
        return self._notes_md_seen

    def begin_tool_turn(self) -> None:
        self._previous_turn_tool_args = list(self._current_turn_tool_args)
        self._current_turn_tool_args = []

    def register_tool_request_args(self, arguments: Any) -> None:
        if isinstance(arguments, dict):
            self._current_turn_tool_args.append(arguments)

    def tool_arguments_for_skill_why(self) -> list[dict[str, Any]]:
        return self._previous_turn_tool_args + self._current_turn_tool_args

    @staticmethod
    def fingerprint_messages(messages: Any) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if not isinstance(messages, list):
            return out
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "")
            content = msg.get("content")
            if isinstance(content, str):
                data = content.encode("utf-8")
            elif content is None:
                data = b""
            else:
                data = json.dumps(content, ensure_ascii=False).encode("utf-8")
            sha = hashlib.sha256(data).hexdigest()
            out.append({"role": role, "sha256": sha})
        return out

    def increment_llm_count(self) -> int:
        self._llm_count += 1
        return self._llm_count
