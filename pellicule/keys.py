from __future__ import annotations

import configparser
from dataclasses import dataclass

from pellicule.settings import keys_file


@dataclass(frozen=True)
class UpstreamCredentials:
    name: str
    base_url: str
    api_key: str


class KeysError(Exception):
    pass


def _read_parser() -> configparser.ConfigParser:
    path = keys_file()
    if not path.is_file():
        raise KeysError(
            f"Fichier de clés introuvable : {path}. Voir README.md (pellicule.keys)."
        )
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    return parser


def provider_names() -> list[str]:
    parser = _read_parser()
    return [s.lower() for s in parser.sections()]


def load_upstream(name: str) -> UpstreamCredentials:
    parser = _read_parser()
    section = name.lower()
    if section not in parser:
        raise KeysError(f"Section [{section}] absente dans {keys_file()}")
    base_url = parser.get(section, "base_url", fallback="").strip().rstrip("/")
    api_key = parser.get(section, "api_key", fallback="").strip()
    if not base_url:
        raise KeysError(f"base_url requis dans [{section}] de {keys_file()}")
    return UpstreamCredentials(name=section, base_url=base_url, api_key=api_key)
