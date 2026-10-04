import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8765
UI_HOST = "127.0.0.1"
UI_PORT = 8766

# Filtres watcher (configurables ; le watcher lit ces listes, pas de motifs en dur dans la logique).
WATCH_IGNORE_SUFFIXES: tuple[str, ...] = (
    ".tmp",
    ".temp",
    ".lock",
    ".swp",
    ".swo",
    "~",
    "desktop.ini",
    "Thumbs.db",
    ".DS_Store",
)

WATCH_IGNORE_DIR_NAMES: tuple[str, ...] = (
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
)

WATCH_TICK_SECONDS: float = 0.35

_TOML_APPLIED = False


@dataclass(frozen=True)
class WatchIgnoreRules:
    suffixes: tuple[str, ...]
    dir_names: tuple[str, ...]


def config_file_path() -> Path:
    raw = os.environ.get("PELLICULE_CONFIG")
    if raw and raw.strip():
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve() / "pellicule.toml"


def _load_toml_dict() -> dict:
    path = config_file_path()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _nested_get(data: dict, *keys: str) -> str | None:
    node: object = data
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if node is None:
        return None
    text = str(node).strip()
    return text if text else None


def _apply_env_from_toml(data: dict) -> None:
    mappings: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("PELLICULE_DATA", ("data", "dir")),
        ("PELLICULE_MERGED_CONFIG", ("policy", "merged_config")),
        ("PELLICULE_AGENTS_DIR", ("policy", "agents_dir")),
        ("PELLICULE_BASE_CONFIG", ("policy", "base_config")),
        ("PELLICULE_WORKSPACE", ("policy", "workspace")),
        ("PELLICULE_CASE_DIR", ("case", "dir")),
        ("PELLICULE_KILO_TASKS_DIR", ("kilo", "tasks_dir")),
    )
    for env_name, path_keys in mappings:
        if os.environ.get(env_name):
            continue
        value = _nested_get(data, *path_keys)
        if value:
            os.environ[env_name] = value

    if not os.environ.get("PELLICULE_WATCH_IGNORE_SUFFIXES"):
        raw = _nested_get(data, "watch", "ignore_suffixes")
        if raw:
            os.environ["PELLICULE_WATCH_IGNORE_SUFFIXES"] = raw

    if not os.environ.get("PELLICULE_WATCH_IGNORE_DIRS"):
        raw = _nested_get(data, "watch", "ignore_dirs")
        if raw:
            os.environ["PELLICULE_WATCH_IGNORE_DIRS"] = raw


def _apply_ports_from_toml_and_env(data: dict) -> None:
    global PROXY_PORT, UI_PORT
    proxy_raw = os.environ.get("PELLICULE_PROXY_PORT")
    if proxy_raw and proxy_raw.strip():
        PROXY_PORT = int(proxy_raw.strip())
    else:
        from_toml = _nested_get(data, "server", "proxy_port")
        if from_toml:
            PROXY_PORT = int(from_toml)

    ui_raw = os.environ.get("PELLICULE_UI_PORT")
    if ui_raw and ui_raw.strip():
        UI_PORT = int(ui_raw.strip())
    else:
        from_toml = _nested_get(data, "server", "ui_port")
        if from_toml:
            UI_PORT = int(from_toml)


def bootstrap_config(
    *,
    proxy_port: int | None = None,
    ui_port: int | None = None,
) -> None:
    """Applique pellicule.toml puis variables d'environnement ; le CLI peut surcharger les ports."""
    global _TOML_APPLIED, PROXY_PORT, UI_PORT
    if _TOML_APPLIED:
        if proxy_port is not None:
            PROXY_PORT = proxy_port
        if ui_port is not None:
            UI_PORT = ui_port
        return

    data = _load_toml_dict()
    _apply_env_from_toml(data)
    _apply_ports_from_toml_and_env(data)
    _TOML_APPLIED = True

    if proxy_port is not None:
        PROXY_PORT = proxy_port
    if ui_port is not None:
        UI_PORT = ui_port


def watch_ignore_rules() -> WatchIgnoreRules:
    suffixes = _csv_env("PELLICULE_WATCH_IGNORE_SUFFIXES", WATCH_IGNORE_SUFFIXES)
    dirs = _csv_env("PELLICULE_WATCH_IGNORE_DIRS", WATCH_IGNORE_DIR_NAMES)
    return WatchIgnoreRules(suffixes=suffixes, dir_names=dirs)


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw or not raw.strip():
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def data_root() -> Path:
    raw = os.environ.get("PELLICULE_DATA")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def sessions_dir() -> Path:
    return data_root() / "sessions"


def keys_file() -> Path:
    return data_root() / "pellicule.keys"


def static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


def case_dir_from_env() -> Path | None:
    raw = os.environ.get("PELLICULE_CASE_DIR")
    if not raw or not raw.strip():
        return None
    path = Path(raw).expanduser().resolve()
    return path if path.is_dir() else None


def reset_bootstrap_for_tests() -> None:
    """Réinitialise l'état du bootstrap (tests uniquement)."""
    global _TOML_APPLIED, PROXY_PORT, UI_PORT
    _TOML_APPLIED = False
    PROXY_PORT = 8765
    UI_PORT = 8766
