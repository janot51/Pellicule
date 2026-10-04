from __future__ import annotations

from pellicule.policy.matchers import normalize_path


def sensitive_env_ask(tool: str, path: str | None) -> bool:
    if tool not in ("read", "write", "edit"):
        return False
    p = normalize_path(path or "")
    if not p:
        return False
    name = p.split("/")[-1]
    if name == ".env.example" or name.endswith(".env.example"):
        return False
    return name == ".env" or name.endswith("/.env")


BUILTIN_ENV_RULE = "builtin: sensitive .env → ask"
