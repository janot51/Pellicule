from __future__ import annotations

import os
import socket
import sys

from pellicule.keys import KeysError, provider_names
from pellicule.kilo_tail import task_storage_roots
from pellicule.policy import load_policy_config
from pellicule.settings import (
    PROXY_HOST,
    PROXY_PORT,
    UI_HOST,
    UI_PORT,
    case_dir_from_env,
    config_file_path,
    data_root,
    keys_file,
)


def _check_port(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
        return True
    except OSError:
        return False


def _validate_keys() -> tuple[bool, list[str]]:
    lines: list[str] = []
    path = keys_file()
    if not path.is_file():
        lines.append(f"ERREUR : fichier de clés introuvable : {path}")
        return False, lines

    try:
        names = provider_names()
    except KeysError as exc:
        lines.append(f"ERREUR : {exc}")
        return False, lines

    if not names:
        lines.append(f"ERREUR : aucune section dans {path}")
        return False, lines

    ok = True
    lines.append(f"OK : {len(names)} fournisseur(s) : {', '.join(names)}")
    from pellicule.keys import load_upstream

    for name in names:
        try:
            cred = load_upstream(name)
            lines.append(f"  [{name}] base_url={cred.base_url}")
            if not cred.base_url:
                ok = False
        except KeysError as exc:
            lines.append(f"  ERREUR [{name}] : {exc}")
            ok = False
    return ok, lines


def run_doctor() -> int:
    print("Pellicule doctor\n")
    keys_ok, key_lines = _validate_keys()
    for line in key_lines:
        print(line)

    if sys.version_info < (3, 11):
        print(f"ERREUR : Python 3.11+ requis (actuel {sys.version.split()[0]})")
        keys_ok = False
    else:
        print(f"OK : Python {sys.version.split()[0]}")

    cfg_path = config_file_path()
    if cfg_path.is_file():
        print(f"OK : config {cfg_path}")
    else:
        print(f"INFO : pas de {cfg_path} (variables d'environnement ou défauts)")

    print(f"OK : données {data_root()}")

    try:
        policy = load_policy_config()
        sources = ", ".join(policy.sources) if policy.sources else "(aucune)"
        print(f"OK : policy config_source={policy.config_source} sources={sources}")
    except Exception as exc:
        print(f"AVERTISSEMENT : chargement policy : {exc}")

    case = case_dir_from_env()
    case_raw = os.environ.get("PELLICULE_CASE_DIR")
    if case:
        print(f"OK : dossier affaire {case}")
    elif case_raw and case_raw.strip():
        print("AVERTISSEMENT : PELLICULE_CASE_DIR défini mais dossier invalide")
    else:
        print("INFO : pas de dossier affaire (PELLICULE_CASE_DIR)")

    proxy_free = _check_port(PROXY_HOST, PROXY_PORT)
    ui_free = _check_port(UI_HOST, UI_PORT)
    if proxy_free:
        print(f"OK : port proxy {PROXY_PORT} disponible")
    else:
        print(f"AVERTISSEMENT : port proxy {PROXY_PORT} déjà utilisé")
    if ui_free:
        print(f"OK : port interface {UI_PORT} disponible")
    else:
        print(f"AVERTISSEMENT : port interface {UI_PORT} déjà utilisé")

    kilo_roots = [r for r in task_storage_roots() if r.is_dir()]
    if kilo_roots:
        for root in kilo_roots:
            print(f"OK : tâches Kilo {root}")
    else:
        print("INFO : aucun dossier de tâches Kilo trouvé (normal si Kilo non installé)")

    return 0 if keys_ok else 1
