# Pellicule

Outil local de profiling d'un harness d'agent (proxy OpenAI-compatible + film des événements).

## Démarrage

```bash
pip install -e .
pellicule
```

- Proxy Kilo : `http://127.0.0.1:8765/v1`
- Interface : `http://127.0.0.1:8766`

## Clés upstream

Créer `pellicule.keys` à la racine du répertoire de travail (fichier ignoré par git) :

```ini
[sidonie]
base_url = https://votre-endpoint-sidonie/v1
api_key = sk-...

[albert]
base_url = https://votre-endpoint-albert/v1
api_key = sk-...
```

Le modèle envoyé par Kilo doit être préfixé (`sidonie/...` ou `albert/...`) pour choisir l'upstream.

## Sessions

Les traces sont écrites dans `sessions/<session_id>/events.jsonl`.

Variable optionnelle `PELLICULE_DATA` : répertoire contenant `sessions/` et `pellicule.keys` (défaut : répertoire courant).

## Policy (jalon 3)

Le proxy charge la config Kilo au démarrage (fichier fusionné, puis repli `agents/*.md` ou `kilo.base.jsonc`). Variables utiles :

- `PELLICULE_MERGED_CONFIG` : chemin vers un `kilo.jsonc` fusionné
- `PELLICULE_AGENTS_DIR` : dossier `agents/` (frontmatter YAML)
- `PELLICULE_BASE_CONFIG` : repli pédagogique
- `PELLICULE_WORKSPACE` : affaire / workspace pour la recherche des configs
- En-tête `X-Pellicule-Mode` : mode actif (`planner`, etc.) pour l'évaluation policy
- `PELLICULE_CASE_DIR` ou en-tête `X-Pellicule-Case-Dir` : dossier d'affaire surveillé (`case_write`)
- Filtres watcher : `PELLICULE_WATCH_IGNORE_SUFFIXES`, `PELLICULE_WATCH_IGNORE_DIRS` (valeurs par défaut dans `settings.py`)
