from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from pellicule.policy.jsonc import loads_jsonc
from pellicule.policy.models import AgentPermissions, FlatRule, LoadedPolicyConfig

_FRONTMATTER = re.compile(r"^---\s*\r?\n(.*?)\r?\n---", re.DOTALL)
_order_counter = 0


def _next_order() -> int:
    global _order_counter
    _order_counter += 1
    return _order_counter


def _reset_order() -> None:
    global _order_counter
    _order_counter = 0


def flatten_permission(permission: Any, source: str) -> list[FlatRule]:
    if not isinstance(permission, dict):
        return []
    rules: list[FlatRule] = []
    for tool, value in permission.items():
        if isinstance(value, str):
            rules.append(FlatRule(tool, "*", value.lower(), source, _next_order()))
        elif isinstance(value, dict):
            for pattern, action in value.items():
                rules.append(
                    FlatRule(tool, str(pattern), str(action).lower(), source, _next_order())
                )
    return rules


def _detect_dialect(data: dict[str, Any]) -> str:
    if "permission" in data or any(
        isinstance(v, dict) and "permission" in v for v in data.get("agent", {}).values()
    ):
        return "v7"
    if "customModes" in data:
        return "legacy"
    return "v7"


def _extract_mcp_tools(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    mcp = data.get("mcp")
    if isinstance(mcp, dict):
        tools = mcp.get("tools")
        if isinstance(tools, list):
            for item in tools:
                if isinstance(item, str):
                    names.add(item)
                elif isinstance(item, dict) and item.get("name"):
                    names.add(str(item["name"]))
    return names


def _parse_agent_markdown(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if not match:
        return {}
    loaded = yaml.safe_load(match.group(1))
    return loaded if isinstance(loaded, dict) else {}


def _agent_body_from_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if match:
        return text[match.end() :].strip()
    return text.strip()


def _extract_slash_commands(data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    block = data.get("command")
    if isinstance(block, dict):
        for key in block:
            if key:
                names.add(str(key).lstrip("/"))
    commands = data.get("commands")
    if isinstance(commands, list):
        for item in commands:
            if isinstance(item, str) and item.strip():
                names.add(item.strip().lstrip("/"))
    return names


def _agent_bodies_from_directory(agents_dir: Path) -> dict[str, str]:
    bodies: dict[str, str] = {}
    if not agents_dir.is_dir():
        return bodies
    for path in sorted(agents_dir.glob("*.md")):
        bodies[path.stem] = _agent_body_from_markdown(path)
    return bodies


def _agents_from_directory(agents_dir: Path) -> dict[str, AgentPermissions]:
    agents: dict[str, AgentPermissions] = {}
    if not agents_dir.is_dir():
        return agents
    for path in sorted(agents_dir.glob("*.md")):
        meta = _parse_agent_markdown(path)
        permission = meta.get("permission")
        name = path.stem
        rules = flatten_permission(permission, f"agents/{path.name}")
        agents[name] = AgentPermissions(name=name, source=f"agents/{path.name}", rules=rules)
    return agents


def _config_from_data(
    data: dict[str, Any],
    *,
    config_source: str,
    primary_source: str,
) -> LoadedPolicyConfig:
    _reset_order()
    dialect = _detect_dialect(data)
    default_agent = str(data.get("default_agent") or data.get("defaultAgent") or "default")
    global_rules = flatten_permission(data.get("permission"), primary_source)
    agents: dict[str, AgentPermissions] = {}
    agent_block = data.get("agent")
    if isinstance(agent_block, dict):
        for name, block in agent_block.items():
            if not isinstance(block, dict):
                continue
            rules = flatten_permission(block.get("permission"), f"{primary_source}#agent.{name}")
            agents[str(name)] = AgentPermissions(
                name=str(name),
                source=f"{primary_source}#agent.{name}",
                rules=rules,
            )
    mcp_tools = _extract_mcp_tools(data)
    agree = config_source == "merged"
    slash_commands = _extract_slash_commands(data)
    agent_bodies: dict[str, str] = {}
    if isinstance(agent_block, dict):
        for name, block in agent_block.items():
            if not isinstance(block, dict):
                continue
            for key in ("prompt", "body", "instructions"):
                val = block.get(key)
                if isinstance(val, str) and val.strip():
                    agent_bodies[str(name)] = val.strip()
                    break
    return LoadedPolicyConfig(
        config_source=config_source,
        dialect=dialect,
        default_agent=default_agent,
        global_rules=global_rules,
        agents=agents,
        mcp_tools=mcp_tools,
        sources=[primary_source],
        agree_without_log=agree,
        agent_bodies=agent_bodies,
        slash_commands=slash_commands,
    )


def _merge_agents_md(
    base: LoadedPolicyConfig,
    agents_dir: Path,
) -> LoadedPolicyConfig:
    md_agents = _agents_from_directory(agents_dir)
    if not md_agents:
        return base
    merged_agents = dict(base.agents)
    for name, agent in md_agents.items():
        if name not in merged_agents:
            merged_agents[name] = agent
    bodies = dict(base.agent_bodies)
    bodies.update(_agent_bodies_from_directory(agents_dir))
    return LoadedPolicyConfig(
        config_source=base.config_source,
        dialect=base.dialect,
        default_agent=base.default_agent,
        global_rules=base.global_rules,
        agents=merged_agents,
        mcp_tools=base.mcp_tools,
        sources=base.sources + [str(agents_dir)],
        agree_without_log=base.agree_without_log,
        agent_bodies=bodies,
        slash_commands=base.slash_commands,
    )


def merged_search_paths(workspace: Path | None) -> list[Path]:
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    paths: list[Path] = [
        home / ".config" / "kilo" / "kilo.jsonc",
        home / ".kilo" / "kilo.jsonc",
        home / ".kilocode" / "kilo.jsonc",
        appdata / "Code" / "User" / "globalStorage" / "kilocode.kilo-code" / "kilo.jsonc",
        appdata / "Code - Insiders" / "User" / "globalStorage" / "kilocode.kilo-code" / "kilo.jsonc",
    ]
    if workspace:
        paths.extend(
            [
                workspace / "kilo.jsonc",
                workspace / ".kilo" / "kilo.jsonc",
                workspace / "kilo.json",
            ]
        )
    env_content = os.environ.get("KILO_CONFIG_CONTENT")
    if env_content:
        paths.append(Path("<KILO_CONFIG_CONTENT>"))
    return paths


def load_policy_config(
    *,
    workspace: Path | None = None,
    agents_dir: Path | None = None,
    base_config: Path | None = None,
) -> LoadedPolicyConfig:
    workspace = workspace or _env_path("PELLICULE_WORKSPACE")
    agents_dir = agents_dir or _env_path("PELLICULE_AGENTS_DIR") or _env_path("AGENT_LAB_HOME")
    if agents_dir and (agents_dir / "agents").is_dir():
        agents_dir = agents_dir / "agents"
    base_config = base_config or _env_path("PELLICULE_BASE_CONFIG")

    explicit = _env_path("PELLICULE_MERGED_CONFIG")
    if explicit and explicit.is_file():
        data = loads_jsonc(explicit.read_text(encoding="utf-8"))
        cfg = _config_from_data(data, config_source="merged", primary_source=str(explicit))
        if agents_dir:
            cfg = _merge_agents_md(cfg, agents_dir)
        return cfg

    kilo_env = os.environ.get("KILO_CONFIG_CONTENT")
    if kilo_env:
        data = loads_jsonc(kilo_env)
        cfg = _config_from_data(
            data, config_source="merged", primary_source="KILO_CONFIG_CONTENT"
        )
        if agents_dir:
            cfg = _merge_agents_md(cfg, agents_dir)
        return cfg

    for candidate in merged_search_paths(workspace):
        if candidate.name == "<KILO_CONFIG_CONTENT>":
            continue
        if candidate.is_file():
            data = loads_jsonc(candidate.read_text(encoding="utf-8"))
            cfg = _config_from_data(data, config_source="merged", primary_source=str(candidate))
            if agents_dir:
                cfg = _merge_agents_md(cfg, agents_dir)
            return cfg

    if agents_dir and agents_dir.is_dir():
        _reset_order()
        agents = _agents_from_directory(agents_dir)
        default_agent = next(iter(agents.keys())) if agents else "default"
        return LoadedPolicyConfig(
            config_source="agents_md",
            dialect="v7",
            default_agent=default_agent,
            global_rules=[],
            agents=agents,
            mcp_tools=set(),
            sources=[str(agents_dir)],
            agree_without_log=False,
            agent_bodies=_agent_bodies_from_directory(agents_dir),
            slash_commands=set(),
        )

    if base_config and base_config.is_file():
        data = loads_jsonc(base_config.read_text(encoding="utf-8"))
        return _config_from_data(data, config_source="base", primary_source=str(base_config))

    return LoadedPolicyConfig(
        config_source="base",
        dialect="v7",
        default_agent="default",
        global_rules=[],
        agents={},
        mcp_tools=set(),
        sources=[],
        agree_without_log=False,
        agent_bodies={},
        slash_commands=set(),
    )


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw or not str(raw).strip():
        return None
    return Path(raw).expanduser().resolve()
