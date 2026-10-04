from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pellicule.policy.models import LoadedPolicyConfig


@dataclass(frozen=True)
class ModeDetection:
    mode: str | None
    confidence: str
    source: str


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def fingerprint_mode(
    system_prompt: str | None,
    agent_bodies: dict[str, str],
) -> ModeDetection:
    if not system_prompt or not str(system_prompt).strip():
        return ModeDetection(None, "unknown", "none")
    norm_sys = _normalize_text(system_prompt)
    best_name: str | None = None
    best_score = 0.0
    for name, body in agent_bodies.items():
        body = (body or "").strip()
        if not body:
            continue
        norm_body = _normalize_text(body)
        if norm_sys == norm_body:
            return ModeDetection(name, "likely", "body_exact")
        if norm_body in norm_sys or norm_sys in norm_body:
            score = len(norm_body) / max(len(norm_sys), 1)
            if score > best_score:
                best_score = score
                best_name = name
        else:
            sys_tokens = set(norm_sys.split())
            body_tokens = set(norm_body.split())
            if not body_tokens:
                continue
            overlap = len(sys_tokens & body_tokens) / len(body_tokens)
            if overlap >= 0.55 and overlap > best_score:
                best_score = overlap
                best_name = name
    if best_name:
        return ModeDetection(best_name, "likely", "body_overlap")
    return ModeDetection(None, "unknown", "body")


def slash_command_from_user_text(
    text: str,
    commands: set[str],
) -> ModeDetection:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return ModeDetection(None, "unknown", "slash")
    token = stripped[1:].split(None, 1)[0].strip()
    if not token:
        return ModeDetection(None, "unknown", "slash")
    key = token.lower()
    for cmd in commands:
        if cmd.lower() == key:
            return ModeDetection(cmd, "likely", "slash")
    return ModeDetection(None, "unknown", "slash")


def slash_command_from_messages(
    messages: Any,
    commands: set[str],
) -> ModeDetection:
    if not isinstance(messages, list):
        return ModeDetection(None, "unknown", "slash")
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            found = slash_command_from_user_text(content, commands)
            if found.mode:
                return found
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    found = slash_command_from_user_text(str(part.get("text", "")), commands)
                    if found.mode:
                        return found
    return ModeDetection(None, "unknown", "slash")


def extract_system_prompt(messages: Any) -> str | None:
    if not isinstance(messages, list):
        return None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            content = msg.get("content")
            if isinstance(content, str):
                return content
    return None


def reconcile_task_mode(
    detected: ModeDetection,
    task_mode: str | None,
) -> ModeDetection:
    if not task_mode:
        return detected
    if not detected.mode:
        return ModeDetection(task_mode, "exact", "kilo_task")
    if detected.mode.lower() == task_mode.lower():
        return ModeDetection(detected.mode, "exact", detected.source)
    return ModeDetection(detected.mode, "contradicted", detected.source)


def detect_mode(
    config: LoadedPolicyConfig,
    messages: Any,
    *,
    task_mode: str | None = None,
) -> ModeDetection:
    system = extract_system_prompt(messages)
    from_body = fingerprint_mode(system, config.agent_bodies)
    from_slash = slash_command_from_messages(messages, config.slash_commands)
    if from_slash.mode:
        base = from_slash
    else:
        base = from_body
    if not base.mode:
        base = ModeDetection(config.default_agent, "unknown", "default")
    return reconcile_task_mode(base, task_mode)
