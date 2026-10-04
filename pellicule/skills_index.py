from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    body: str
    rel_path: str


def _parse_skill_file(path: Path, root: Path) -> SkillEntry | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _FRONTMATTER.match(text)
    if not match:
        return None
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        return None
    name = str(meta.get("name") or path.parent.name)
    description = str(meta.get("description") or "")
    body = text[match.end() :].strip()
    rel = path.relative_to(root).as_posix()
    return SkillEntry(name=name, description=description, body=body, rel_path=rel)


def load_skills_from_paths(paths: list[Path]) -> list[SkillEntry]:
    entries: list[SkillEntry] = []
    seen: set[str] = set()
    for base in paths:
        if not base.is_dir():
            continue
        for skill_md in sorted(base.rglob("SKILL.md")):
            entry = _parse_skill_file(skill_md, base)
            if entry and entry.name not in seen:
                seen.add(entry.name)
                entries.append(entry)
    return entries


def load_skills_from_config(config: dict[str, Any]) -> list[SkillEntry]:
    paths_block = config.get("skills")
    paths: list[Path] = []
    if isinstance(paths_block, dict):
        raw_paths = paths_block.get("paths")
        if isinstance(raw_paths, list):
            for item in raw_paths:
                if isinstance(item, str) and item.strip():
                    paths.append(Path(item).expanduser())
    return load_skills_from_paths(paths)


def skill_body_newly_in_system(
    body: str,
    system_text: str,
    previous_system: str | None,
    *,
    min_chars: int = 200,
) -> bool:
    if len(body) < min_chars:
        return False
    if body not in system_text:
        return False
    if previous_system and body in previous_system:
        return False
    return True
