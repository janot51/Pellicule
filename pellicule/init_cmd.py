from __future__ import annotations

from pathlib import Path

from pellicule.settings import config_file_path, keys_file

DEFAULT_TOML = """# Configuration Pellicule (voir pellicule.toml.example)
# Les variables d'environnement PELLICULE_* remplacent ces valeurs.

[data]
# Répertoire contenant sessions/ et pellicule.keys (défaut : répertoire courant)
# dir = "."

[server]
proxy_port = 8765
ui_port = 8766

# [policy]
# merged_config = "chemin/vers/kilo.jsonc"
# agents_dir = "chemin/vers/agents"
# base_config = "chemin/vers/kilo.base.jsonc"
# workspace = "chemin/vers/workspace"

# [case]
# dir = "chemin/vers/affaire"

# [kilo]
# tasks_dir = "chemin/vers/tasks"

# [watch]
# ignore_suffixes = ".tmp,.lock"
# ignore_dirs = ".git,node_modules"
"""

DEFAULT_KEYS_TEMPLATE = """# Fichier de clés upstream (ignoré par git)
# Préfixez le modèle Kilo : sidonie/model-name ou albert/model-name

[{provider}]
base_url = {base_url}
{api_key_line}
"""


def run_init(
    *,
    force: bool = False,
    data_dir: str | None = None,
    case_dir: str | None = None,
    workspace: str | None = None,
    merged_config: str | None = None,
    agents_dir: str | None = None,
    provider: str = "default",
    base_url: str = "https://votre-endpoint/v1",
    api_key: str | None = None,
) -> int:
    toml_path = config_file_path()
    if data_dir:
        import os

        os.environ["PELLICULE_DATA"] = str(Path(data_dir).expanduser().resolve())

    keys_path = keys_file()
    keys_path.parent.mkdir(parents=True, exist_ok=True)

    if toml_path.is_file() and not force:
        print(f"Déjà présent : {toml_path} (utilisez --force pour écraser)")
    else:
        content = DEFAULT_TOML
        extra_lines: list[str] = []
        if data_dir:
            extra_lines.append(f'dir = "{Path(data_dir).as_posix()}"')
        if extra_lines:
            content = content.replace(
                "# dir = \".\"",
                "\n".join(extra_lines),
            )
        if case_dir or workspace or merged_config or agents_dir:
            policy_block: list[str] = ["\n[policy]"]
            if merged_config:
                policy_block.append(f'merged_config = "{merged_config}"')
            if agents_dir:
                policy_block.append(f'agents_dir = "{agents_dir}"')
            if workspace:
                policy_block.append(f'workspace = "{workspace}"')
            if case_dir:
                content = content.replace(
                    "# [case]",
                    "[case]\n" + f'dir = "{case_dir}"\n\n# [case]',
                )
            content = content.replace(
                "# [policy]",
                "\n".join(policy_block),
            )
        toml_path.write_text(content, encoding="utf-8")
        print(f"Créé : {toml_path}")

    api_key_line = f"api_key = {api_key}" if api_key else "# api_key = sk-..."
    keys_content = DEFAULT_KEYS_TEMPLATE.format(
        provider=provider,
        base_url=base_url,
        api_key_line=api_key_line,
    )
    if keys_path.is_file() and not force:
        print(f"Déjà présent : {keys_path} (utilisez --force pour écraser)")
    else:
        keys_path.write_text(keys_content, encoding="utf-8")
        print(f"Créé : {keys_path}")

    print("\nÉditez pellicule.keys puis lancez : pellicule doctor")
    return 0
