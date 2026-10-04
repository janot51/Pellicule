from __future__ import annotations

import re
from typing import Any

from pellicule.skills_index import load_skills_from_config

_FRONTMATTER = re.compile(r"^---\s*\r?\n(.*?)\r?\n---", re.DOTALL)

_KIND_PRIORITY = {
    "skill_body": 0,
    "agent_prompt": 1,
    "command_template": 2,
    "skill_catalogue": 3,
    "unknown": 4,
}


def _agent_prompts(config: dict[str, Any]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    agents = config.get("agent")
    if not isinstance(agents, dict):
        return out
    for name, block in agents.items():
        if not isinstance(block, dict):
            continue
        for key in ("prompt", "body", "instructions"):
            val = block.get(key)
            if isinstance(val, str) and val.strip():
                out.append((str(name), val, f"prompt agent {name}"))
                break
    return out


def _command_templates(config: dict[str, Any]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    block = config.get("command")
    if not isinstance(block, dict):
        return out
    for name, spec in block.items():
        if not isinstance(spec, dict):
            continue
        tpl = spec.get("template")
        if isinstance(tpl, str) and tpl.strip():
            out.append((str(name), tpl, f"commande /{name}"))
    return out


def _catalogue_entries(skills: list[SkillEntry]) -> list[tuple[str, str, str]]:
    return [(s.name, s.description, f"catalogue skill {s.name}") for s in skills if s.description]


def _skill_bodies(skills: list[SkillEntry]) -> list[tuple[str, str, str]]:
    return [(s.name, s.body, f"corps skill {s.name}") for s in skills if s.body]


def _find_candidates(system_text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    skills = load_skills_from_config(config)
    candidates: list[tuple[str, str, str, str]] = []
    for name, text, label in _agent_prompts(config):
        candidates.append(("agent_prompt", name, text, label))
    for name, text, label in _command_templates(config):
        candidates.append(("command_template", name, text, label))
    for name, text, label in _skill_bodies(skills):
        candidates.append(("skill_body", name, text, label))
    for name, text, label in _catalogue_entries(skills):
        candidates.append(("skill_catalogue", name, text, label))

    found: list[dict[str, Any]] = []
    for kind, _name, needle, label in candidates:
        if not needle or needle not in system_text:
            continue
        start = 0
        while True:
            idx = system_text.find(needle, start)
            if idx < 0:
                break
            found.append(
                {
                    "kind": kind,
                    "label": label,
                    "start": idx,
                    "end": idx + len(needle),
                }
            )
            start = idx + 1
    return found


def _resolve_overlaps(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not found:
        return []
    found = sorted(found, key=lambda b: (-(b["end"] - b["start"]), _KIND_PRIORITY.get(b["kind"], 99), b["start"]))
    kept: list[dict[str, Any]] = []
    for block in found:
        overlap = False
        for other in kept:
            if block["start"] < other["end"] and block["end"] > other["start"]:
                overlap = True
                break
        if not overlap:
            kept.append(block)
    kept.sort(key=lambda b: b["start"])
    return kept


def compute_prompt_blocks(system_text: str | None, config: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not system_text or not config:
        return []
    matched = _resolve_overlaps(_find_candidates(system_text, config))
    covered = [(b["start"], b["end"]) for b in matched]
    covered.sort()
    blocks = list(matched)
    pos = 0
    for start, end in covered:
        if start > pos:
            blocks.append(
                {
                    "kind": "unknown",
                    "label": "bloc non reconnu",
                    "start": pos,
                    "end": start,
                }
            )
        pos = max(pos, end)
    if pos < len(system_text):
        blocks.append(
            {
                "kind": "unknown",
                "label": "bloc non reconnu",
                "start": pos,
                "end": len(system_text),
            }
        )
    blocks.sort(key=lambda b: b["start"])
    return blocks
