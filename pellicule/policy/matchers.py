from __future__ import annotations

import fnmatch
import re
from typing import Any


def normalize_path(path: str | None) -> str:
    if not path:
        return ""
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("/"):
        p = p[1:]
    return p


def glob_path_match(pattern: str, path: str) -> bool:
    path = normalize_path(path)
    pattern = pattern.replace("\\", "/").lstrip("./")
    if pattern == "*":
        return True
    if "**" not in pattern:
        return fnmatch.fnmatchcase(path, pattern)
    head, tail = pattern.split("**", 1)
    head = head.rstrip("/")
    tail = tail.lstrip("/")
    if head and path != head and not path.startswith(head + "/"):
        return False
    rest = path[len(head) :].lstrip("/") if head else path
    if tail in ("", "*"):
        return True
    if fnmatch.fnmatchcase(rest, tail):
        return True
    if "/" in rest and fnmatch.fnmatchcase(rest.split("/")[-1], tail):
        return True
    return fnmatch.fnmatchcase(rest, f"*/{tail}")


def bash_pattern_match(pattern: str, command: str) -> bool:
    command = command.strip()
    pattern = pattern.replace("\\", "/")
    return fnmatch.fnmatchcase(command, pattern)


def extract_tool_context(tool: str, arguments: Any) -> tuple[str | None, str | None, str | None]:
    path: str | None = None
    command: str | None = None
    task_agent: str | None = None
    if isinstance(arguments, dict):
        for key in ("path", "file_path", "filepath", "target_file"):
            if key in arguments and arguments[key]:
                path = str(arguments[key])
                break
        if "command" in arguments and arguments["command"]:
            command = str(arguments["command"])
        for key in ("agent", "subagent", "name", "mode"):
            if key in arguments and arguments[key]:
                task_agent = str(arguments[key])
                break
    return path, command, task_agent


def normalize_motif(tool: str, arguments: Any) -> str:
    path, command, task_agent = extract_tool_context(tool, arguments)
    if tool == "task" and task_agent:
        return f"task:{task_agent}"
    if tool == "bash" and command:
        segment = command.strip().split(None, 1)[0] if command.strip() else command
        return f"bash:{segment}"
    if path:
        return f"{tool}:{normalize_path(path)}"
    if command:
        return f"{tool}:{command.strip()}"
    if isinstance(arguments, dict):
        return f"{tool}:{normalize_path(str(arguments))}"
    return f"{tool}:"


def rule_matches(
    rule_tool: str,
    rule_pattern: str,
    tool: str,
    path: str | None,
    command: str | None,
    task_agent: str | None,
) -> bool:
    if rule_tool != tool:
        return False
    if rule_pattern == "*":
        return True
    if tool in ("read", "write", "edit", "delete", "list"):
        return glob_path_match(rule_pattern, path or "")
    if tool == "bash":
        return bash_pattern_match(rule_pattern, command or "")
    if tool == "task":
        return glob_path_match(rule_pattern, task_agent or "") or rule_pattern == task_agent
    return glob_path_match(rule_pattern, path or command or task_agent or "")
