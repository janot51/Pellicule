import os
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


@dataclass(frozen=True)
class WatchIgnoreRules:
    suffixes: tuple[str, ...]
    dir_names: tuple[str, ...]


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
