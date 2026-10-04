from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from pellicule import schema
from pellicule.policy.ask_state import tool_message_indicates_rejection
from pellicule.policy.models import LoadedPolicyConfig, PolicyEvaluation
from pellicule.session import SessionStore

_PERMISSION_DENIED = re.compile(
    r"permission\s+denied\s*:\s*(\w+)\s+(.+)",
    re.IGNORECASE,
)
_ASK_PENDING = re.compile(r"(approval\s+required|ask\s+permission)", re.IGNORECASE)

RecordFn = Callable[[dict[str, Any]], Awaitable[None]]


def task_storage_roots() -> list[Path]:
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    roots: list[Path] = [
        appdata / "Code" / "User" / "globalStorage" / "kilocode.kilo-code" / "tasks",
        appdata
        / "Code - Insiders"
        / "User"
        / "globalStorage"
        / "kilocode.kilo-code"
        / "tasks",
        home / ".kilocode" / "cli" / "logs",
    ]
    custom = os.environ.get("PELLICULE_KILO_TASKS_DIR")
    if custom:
        roots.insert(0, Path(custom).expanduser().resolve())
    return roots


def read_json_defensive(path: Path) -> Any | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def list_active_task_dirs(
    roots: list[Path],
    *,
    since_ts: float | None = None,
) -> list[tuple[Path, float]]:
    found: list[tuple[Path, float]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            try:
                mtime = max(
                    child.stat().st_mtime,
                    *(
                        p.stat().st_mtime
                        for p in child.glob("*.json")
                        if p.is_file()
                    ),
                )
            except OSError:
                continue
            if since_ts is not None and mtime < since_ts:
                continue
            found.append((child, mtime))
    found.sort(key=lambda item: item[1], reverse=True)
    return found


@dataclass(frozen=True)
class ParsedKiloLog:
    raw: str
    verdict: str | None
    tool: str | None
    path: str | None
    parsed: bool


def parse_permission_line(text: str) -> ParsedKiloLog:
    stripped = text.strip()
    if not stripped:
        return ParsedKiloLog(stripped, None, None, None, False)
    denied = _PERMISSION_DENIED.search(stripped)
    if denied:
        return ParsedKiloLog(
            stripped,
            "deny",
            denied.group(1).lower(),
            denied.group(2).strip(),
            True,
        )
    if _ASK_PENDING.search(stripped):
        return ParsedKiloLog(stripped, "ask", None, None, True)
    lower = stripped.lower()
    if "allowed" in lower or "executing tool" in lower:
        return ParsedKiloLog(stripped, "allow", None, None, True)
    return ParsedKiloLog(stripped, None, None, None, False)


def iter_log_strings(node: Any) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        if node.strip():
            out.append(node)
        return out
    if isinstance(node, dict):
        for key in ("content", "text", "message", "error", "stderr", "stdout"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val)
        for key in ("messages", "history", "items", "conversation", "data"):
            child = node.get(key)
            if isinstance(child, list):
                for item in child:
                    out.extend(iter_log_strings(item))
        return out
    if isinstance(node, list):
        for item in node:
            out.extend(iter_log_strings(item))
    return out


def collect_task_log_lines(task_dir: Path) -> list[str]:
    lines: list[str] = []
    for name in ("api_conversation_history.json", "ui_messages.json"):
        path = task_dir / name
        if not path.is_file():
            continue
        data = read_json_defensive(path)
        if data is None:
            continue
        lines.extend(iter_log_strings(data))
    return lines


def mode_from_task_dir(task_dir: Path) -> str | None:
    for name in ("api_conversation_history.json", "task.json", "ui_messages.json"):
        path = task_dir / name
        data = read_json_defensive(path) if path.is_file() else None
        if data is None:
            continue
        mode = _extract_mode_from_json(data)
        if mode:
            return mode
    return None


def _extract_mode_from_json(node: Any) -> str | None:
    if isinstance(node, dict):
        for key in ("mode", "agent", "customAgent", "custom_agent", "activeAgent"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for child in node.values():
            found = _extract_mode_from_json(child)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _extract_mode_from_json(item)
            if found:
                return found
    return None


def _paths_compatible(local: str | None, kilo: str | None) -> bool:
    if not local or not kilo:
        return True
    a = local.replace("\\", "/").strip().lower()
    b = kilo.replace("\\", "/").strip().lower()
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def click_choice_from_log(parsed: ParsedKiloLog, raw: str) -> str:
    lower = raw.lower()
    if parsed.verdict == "deny" or tool_message_indicates_rejection(raw):
        return "reject"
    if parsed.verdict == "allow":
        if "once" in lower:
            return "allow_once"
        if "toujours" in lower or "always" in lower:
            return "allow_always"
        return "allow"
    return "allow"


def reconcile_verdicts(
    evaluation: PolicyEvaluation,
    parsed: ParsedKiloLog,
    *,
    mode_confidence: str | None,
) -> tuple[bool, str | None]:
    if not parsed.parsed:
        return False, "log_unparsed"
    if parsed.verdict is None:
        return False, "log_unparsed"
    if parsed.verdict != evaluation.verdict:
        if evaluation.dialect == "legacy" and evaluation.tool == "read":
            return False, "dialect_legacy"
        if mode_confidence in (None, "unknown", "likely"):
            return False, "mode_unknown"
        return False, "precedence"
    if parsed.tool and parsed.tool != evaluation.tool:
        return False, "precedence"
    if not _paths_compatible(evaluation.path, parsed.path):
        return False, "precedence"
    return True, None


@dataclass
class PendingKiloMatch:
    tool_call_id: str
    tool: str
    evaluation: PolicyEvaluation
    policy_detail: dict[str, Any]
    mode: str | None
    mode_confidence: str | None
    recorded_at: str


@dataclass
class KiloTailCoordinator:
    store: SessionStore
    config: LoadedPolicyConfig
    record: RecordFn
    poll_seconds: float = 0.5
    _pending: dict[str, PendingKiloMatch] = field(default_factory=dict)
    _seen_raw: set[str] = field(default_factory=set)
    _session_started: float = field(default_factory=lambda: 0.0)
    _task_roots: list[Path] = field(default_factory=task_storage_roots)
    _running: bool = False

    def latest_task_mode(self) -> str | None:
        for task_dir, _mtime in list_active_task_dirs(self._task_roots):
            mode = mode_from_task_dir(task_dir)
            if mode:
                return mode
        return None

    def register_policy(
        self,
        *,
        tool_call_id: str,
        tool: str,
        evaluation: PolicyEvaluation,
        policy_detail: dict[str, Any],
        mode: str | None,
        mode_confidence: str | None,
    ) -> None:
        self._pending[tool_call_id] = PendingKiloMatch(
            tool_call_id=tool_call_id,
            tool=tool,
            evaluation=evaluation,
            policy_detail=dict(policy_detail),
            mode=mode,
            mode_confidence=mode_confidence,
            recorded_at=schema.utc_now_iso(),
        )

    async def run(self) -> None:
        import time

        self._session_started = time.time()
        self._running = True
        while self._running:
            await self._poll_once()
            await asyncio.sleep(self.poll_seconds)

    def stop(self) -> None:
        self._running = False

    async def _poll_once(self) -> None:
        if not self._pending:
            return
        active = list_active_task_dirs(self._task_roots, since_ts=self._session_started - 60.0)
        ambiguous = len(active) > 1
        for task_dir, _mtime in active:
            for raw in collect_task_log_lines(task_dir):
                if raw in self._seen_raw:
                    continue
                self._seen_raw.add(raw)
                parsed = parse_permission_line(raw)
                if not parsed.parsed and "permission" not in raw.lower():
                    await self._emit_kilo_log(raw, task_dir, ambiguous)
                    continue
                await self._try_match(raw, parsed, task_dir, ambiguous)

    async def _emit_kilo_log(self, raw: str, task_dir: Path, ambiguous: bool) -> None:
        sid = self.store.session_id
        if not sid:
            return
        turn = self.store.next_turn()
        event = schema.build_event(
            session_id=sid,
            layer="kilo_log",
            turn=turn,
            model=None,
            summary="kilo_log_brut",
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            detail={
                "raw": raw,
                "task_dir": str(task_dir),
                "ambiguous_task": ambiguous,
            },
            parent_session_id=self.store.parent_session_id,
            case_dir=self.store.case_dir,
        )
        await self.record(event)

    async def _try_match(
        self,
        raw: str,
        parsed: ParsedKiloLog,
        task_dir: Path,
        ambiguous: bool,
    ) -> None:
        matched_id: str | None = None
        for call_id, pending in list(self._pending.items()):
            if parsed.tool and parsed.tool != pending.tool:
                continue
            if parsed.path and pending.evaluation.path:
                if not _paths_compatible(pending.evaluation.path, parsed.path):
                    continue
            matched_id = call_id
            break
        if matched_id is None:
            for call_id, pending in self._pending.items():
                if parsed.tool is None or parsed.tool == pending.tool:
                    matched_id = call_id
                    break
        if matched_id is None:
            if not parsed.parsed:
                await self._emit_kilo_log(raw, task_dir, ambiguous)
            return

        pending = self._pending.pop(matched_id, None)
        if pending is None:
            return
        agree, hypothesis = reconcile_verdicts(
            pending.evaluation,
            parsed,
            mode_confidence=pending.mode_confidence,
        )
        if not agree and hypothesis is None:
            hypothesis = "rule_not_in_loaded_config"

        choice = click_choice_from_log(parsed, raw)
        click_detail: dict[str, Any] = {
            "raw": raw,
            "tool": pending.tool,
            "tool_call_id": matched_id,
            "choice": choice,
            "agree": agree,
        }
        if not agree and hypothesis:
            click_detail["hypothesis"] = hypothesis
        if ambiguous:
            click_detail["ambiguous_task"] = True
        task_mode = mode_from_task_dir(task_dir)
        if task_mode:
            click_detail["kilo_task_mode"] = task_mode

        sid = self.store.ensure_session()
        turn = self.store.next_turn()
        event = schema.build_event(
            session_id=sid,
            layer="click",
            turn=turn,
            model=None,
            summary=f"click {choice} {pending.tool}",
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            tool_call_id=matched_id,
            detail=click_detail,
            mode=pending.mode,
            mode_confidence=pending.mode_confidence,
            case_dir=self.store.case_dir,
            parent_session_id=self.store.parent_session_id,
        )
        await self.record(event)

    def apply_immediate_log(
        self,
        *,
        tool_call_id: str,
        raw_line: str,
        mode_confidence: str | None = None,
    ) -> dict[str, Any] | None:
        """Applique une ligne Kilo déjà connue (tests / rejeu assisté)."""
        pending = self._pending.get(tool_call_id)
        if pending is None:
            return None
        parsed = parse_permission_line(raw_line)
        agree, hypothesis = reconcile_verdicts(
            pending.evaluation,
            parsed,
            mode_confidence=mode_confidence or pending.mode_confidence,
        )
        choice = click_choice_from_log(parsed, raw_line)
        detail = {
            "raw": raw_line,
            "tool": pending.tool,
            "tool_call_id": tool_call_id,
            "choice": choice,
            "agree": agree,
        }
        if not agree and hypothesis:
            detail["hypothesis"] = hypothesis
        self._pending.pop(tool_call_id, None)
        return detail
