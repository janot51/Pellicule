# Pellicule

Outil local de profiling d'un harness d'agent (proxy OpenAI-compatible + film des événements).

## Installation rapide (Windows)

```powershell
.\install.ps1
```

Le script vérifie Python 3.11+, crée un venv, installe le paquet et lance `pellicule init` si besoin.

## Installation manuelle

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate
pip install -e .
pellicule init
pellicule doctor
pellicule
```

- Proxy Kilo : `http://127.0.0.1:8765/v1`
- Interface : `http://127.0.0.1:8766` (ouvrir cette URL, pas le fichier HTML ; recharger avec Ctrl+F5 après mise à jour)

## Configuration

Priorité : **options CLI** > **variables `PELLICULE_*`** > **`pellicule.toml`** > **défauts**.

1. Copiez [`pellicule.toml.example`](pellicule.toml.example) vers `pellicule.toml` (ou `pellicule init`).
2. Copiez [`pellicule.keys.example`](pellicule.keys.example) vers `pellicule.keys` dans le répertoire de données.

Exemple `pellicule.toml` :

```toml
[data]
dir = "."

[policy]
merged_config = "chemin/vers/kilo.jsonc"
agents_dir = "agents"
workspace = "C:/mon/workspace"

[case]
dir = "C:/mon/affaire"
```

### Clés upstream (`pellicule.keys`)

```ini
[sidonie]
base_url = https://votre-endpoint-sidonie/v1

[albert]
base_url = https://votre-endpoint-albert/v1
api_key = sk-...
```

Le modèle envoyé par Kilo choisit l'upstream par préfixe (`sidonie/...` ou `albert/...`). Sans préfixe, Kilo envoie l'identifiant nu (`deepseek-v4-flash`) : il est relayé vers la section `[pellicule]` lorsqu'elle existe. Un identifiant déjà qualifié (`org/model`) dont le préfixe n'est pas une section connue n'est pas réécrit.

### Commandes utiles

| Commande | Rôle |
|----------|------|
| `pellicule` / `pellicule serve` | Lance proxy + interface |
| `pellicule init` | Crée `pellicule.toml` et `pellicule.keys` (`--force` pour écraser) |
| `pellicule doctor` | Vérifie clés, policy, ports, dossiers Kilo |

Ports : `--proxy-port`, `--ui-port` ou `[server]` dans le TOML, ou `PELLICULE_PROXY_PORT` / `PELLICULE_UI_PORT`.

## Sessions

Les traces sont écrites dans `sessions/<session_id>/events.jsonl` sous le répertoire de données (`[data] dir` ou `PELLICULE_DATA`, défaut : répertoire courant).

## Policy

Le proxy charge la config Kilo au démarrage (fichier fusionné, puis repli `agents/*.md` ou `kilo.base.jsonc`). Équivalents TOML sous `[policy]` :

- `merged_config` → `PELLICULE_MERGED_CONFIG`
- `agents_dir` → `PELLICULE_AGENTS_DIR`
- `base_config` → `PELLICULE_BASE_CONFIG`
- `workspace` → `PELLICULE_WORKSPACE`

En-têtes HTTP : `X-Pellicule-Mode`, `X-Pellicule-Case-Dir`. Dossier affaire : `[case] dir` ou `PELLICULE_CASE_DIR`. Filtres watcher : `[watch]` ou `PELLICULE_WATCH_IGNORE_SUFFIXES` / `PELLICULE_WATCH_IGNORE_DIRS`.

Chemin du fichier TOML : `PELLICULE_CONFIG` (sinon `./pellicule.toml`).
