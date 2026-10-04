from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def strip_jsonc(text: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    escape = False
    in_line_comment = False
    in_block_comment = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def loads_jsonc(text: str) -> dict:
    cleaned = strip_jsonc(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("JSONC root must be an object")
    return data


def permission_object_for_tool(rule_source: str, tool: str) -> dict[str, Any] | None:
    """Retourne l'objet permission d'un outil (pas le fichier entier)."""
    if not rule_source or not tool:
        return None
    path_part = rule_source.split("#", 1)[0]
    fragment = rule_source.split("#", 1)[1] if "#" in rule_source else ""
    path = Path(path_part)
    if not path.is_file():
        return None
    data = loads_jsonc(path.read_text(encoding="utf-8"))
    permission: Any = None
    if fragment.startswith("agent."):
        parts = fragment.split(".")
        if len(parts) >= 2:
            agent_name = parts[1]
            agent_block = data.get("agent")
            if isinstance(agent_block, dict):
                agent = agent_block.get(agent_name)
                if isinstance(agent, dict):
                    permission = agent.get("permission")
    else:
        permission = data.get("permission")
    if not isinstance(permission, dict):
        return None
    entry = permission.get(tool)
    if isinstance(entry, dict):
        return entry
    return None
