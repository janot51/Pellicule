# Pellicule — spec produit

Outil local de profiling d'un harness d'agent. Premier client : Agent Lab
(`janot51/agent-lab`, Kilo Code, VS Code, modèles OpenAI-compatibles Sidonie
CNES et Albert DINUM). Le modèle de données reste réutilisable sur un autre
projet agentique, à condition que ce projet ait une config de permissions
rejouable et une trace de tool calls.

Nom retenu : **Pellicule**. Le film des couches, pas un tableau de bord.
Paquet Python `pellicule`, commande `pellicule`, page `http://127.0.0.1:8766`.
Titre de travail abandonné : Harness Lens.

Pas un chatbot. Pas un remplacement de Kilo. Pas un Langfuse. Un film des
layers, en direct, puis rejouable sans rappeler le modèle.

## Deux objectifs, un seul artefact

1. **Pédagogie.** Former l'auteur et expliquer le harness à quelqu'un du labo
   qui n'a pas écrit les règles. Chaque ligne porte le nom du layer et une
   légende fixe. Last-match-wins ne s'enseigne qu'avec les règles qui ont
   aussi matché et perdu.
2. **Optimisation d'Agent Lab.** Décider, sans rappeler Sidonie : une deny
   fait-elle réessayer le modèle, une règle ne matche-t-elle jamais, un mode
   compacte-t-il trop tôt, Sidonie est-elle plus lente qu'Albert sur ce mode.
   Le jet 1 n'a pas de graphiques. Le jsonl doit porter de quoi les calculer
   après coup.

Les deux objectifs partagent le même événement. On n'écrit pas deux traces.

## Décisions déjà prises

- UI : une page web sur localhost, à côté de VS Code. Pas de webview au
  premier jet. Un seul processus Python. Pas de second outil à ouvrir.
- Sources : les trois. Proxy pour les appels LLM. Moteur de policy qui rejoue
  la config fusionnée. Tail des logs et du JSON de tâche Kilo. Watcher sur
  le dossier d'affaire.
- Mode d'usage : live, et enregistrement rejouable sans Sidonie ni Albert.
- Souverain : rien ne sort de la machine. Pas de télémétrie, pas de SaaS,
  pas de clé dans le dépôt Agent Lab.
- Le flush avant compaction et son automatisation sont hors scope. Détecter
  qu'une compaction a eu lieu, et montrer ce qui a rétréci, oui.
- `ask` est dans le jet 1. Quatre états, pas trois.
- Film imbriqué seulement pour un `task` autorisé. Une commande `/` est un
  changement de mode dans la même session, pas une fille.
- Vérité policy par défaut : le `kilo.jsonc` fusionné par
  `detect_kilo.py --apply`. `agents/*.md` est la provenance affichée, pas la
  seule source. À confirmer au moment du vibe coding si le fichier fusionné
  est introuvable.
- Rétention : hash + taille + 2 Ko de tête. Corps complet seulement sur
  deny, ask, et compaction.
- Rejeu : uniquement les `events.jsonl` écrits par le proxy Pellicule.
  Pas de reconstruction de l'historique Kilo antérieur au lancement.
- Concurrence : une seule instance VS Code / Kilo active. Un seul client
  sur le port 8765. Pas de multiplexage multi-workspace au jet 1.
- Entêtement : une deny suivie du même outil sur le même motif est un
  événement de répétition, visible dans le film. C'est le coût à optimiser.
- Watcher : ignore temporaires, locks et caches. Le film ne montre que
  les fichiers d'affaire.
- Moteur de policy : zéro règle Agent Lab en dur. Il lit YAML/JSONC. Les
  cinq denies du scénario sont des fixtures, pas des branches du binaire.
- IHM : page statique, densité type Linear, sombre. Pas un HUD décoratif.
  Les couleurs d'état sont le cours, pas la décoration.

## Ce qu'on ne réinvente pas

Le film LLM existe déjà. La couche qui n'existe nulle part est le recalcul
de la règle Kilo, corrélé au `tool_call_id`, confirmé ou contredit par le
log.

| Outil | Idée à reprendre | Ne pas vendorer |
|---|---|---|
| cctrace | Barre de trajectoire, frontières de compaction, rejeu qui suit le live | Proxy TLS, cibles Claude Code / Codex |
| agent-trail | Lecture seule de JSONL locaux, outil et résultat dans le même tour | Dépendance à un transcript Claude |
| Rewind | Time-travel local, SQLite, rien ne sort | Fork qui rappelle le modèle |
| Helicone, LiteLLM | Un changement de base URL suffit pour voir le POST | Ne voient pas la deny |
| Langfuse, Phoenix | Spans, tokens, rejeu | Elastic / ClickHouse, Docker, pas le dialecte Kilo |

On copie les idées dans une page statique. On n'importe pas ces projets.
Phoenix est en Elastic License 2.0. Langfuse tire une stack qu'on ne veut
pas sur un poste Windows sans Docker.

## Pourquoi trois sources

Un proxy ne voit que ce que le modèle envoie et reçoit. Une deny rule vit
dans Kilo, entre le tool call et l'exécution. La doc Kilo ne met pas le nom
de la règle dans le message renvoyé au modèle. Si l'erreur ne nomme pas la
règle, le proxy ne peut pas l'inventer.

Donc, pour chaque tool call :

1. Le proxy enregistre la demande et le message `tool` du tour suivant.
2. Le moteur de policy relit la config du mode actif et recalcule la règle
   qui gagne, plus celles qui ont matché et perdu.
3. Le tail des fichiers de tâche Kilo confirme ou contredit ce calcul.
   L'UI montre les deux, jamais un seul fondu dans l'autre.

`agree` est faux quand le calcul local et le log Kilo divergent. L'UI le
marque en rouge. C'est le cas qui apprend : soit la spec de précédence est
fausse, soit Kilo a appliqué une règle que la config chargée ne contient
pas. Un deny que Kilo n'applique pas est déjà arrivé (lecture de `.env`
malgré un deny). Le rouge n'est pas une erreur d'affichage.

## Utilisateurs

- L'auteur, en train de modifier `agents/*.md` ou `kilo.base.jsonc`.
- Un ingénieur du labo à qui on explique pourquoi l'agent n'a pas lu le PDF.
- Plus tard, Cursor, qui reçoit le jsonl d'une session, pas une capture.

Le vocabulaire de l'UI est en français. Les noms de layers restent en
anglais, stables, parce qu'ils sont le schéma.

## Layers

Un tour n'est pas un appel LLM. Un tour est cette chaîne.

| Layer | Quoi | Source | Légende fixe, toujours visible |
|---|---|---|---|
| `llm` | POST chat completions, rôles des messages, usage, latence | Proxy | Le modèle a reçu ce contexte et a répondu. |
| `tool_request` | Nom, arguments, `tool_call_id` | Corps de la réponse assistant | Le modèle a demandé un outil. Ce n'est pas encore une action. |
| `policy` | allow / deny / ask, règle gagnante, perdants, motif, mode, dialecte | Config rejouée + log Kilo | Kilo a tranché avant d'exécuter. La dernière règle qui matche gagne. |
| `exec` | Exécution réelle ou pas, durée, octets, code, état ask | Message `tool` suivant, ou log | L'outil a tourné, ou le harness l'a arrêté. |
| `case_write` | Fichier d'affaire créé ou modifié | Watcher | Le dossier d'affaire a bougé. Seule preuve hors du modèle. |
| `compact` | Appel de résumé, historique qui rétrécit, prune d'un tool result | Proxy + diff de l'historique | Le contexte a été résumé. Ce qui n'était pas dans NOTES.md est perdu. |
| `mode` | Changement d'agent dans la même session | Empreinte du system prompt, puis JSON de tâche | Ce n'est pas un sous-agent. La commande `/` a changé les droits. |
| `kilo_log` | Ligne brute si le format est inconnu | Tail | Source non comprise. On ne l'invente pas. |

Corrélation obligatoire : `tool_call_id`, sinon horodatage plus nom d'outil.
Un deny sans exécution est un succès de harness, pas un trou du film.
Un appel MCP (`doc_extract`, `doc_describe_image`, `doc_check_citations`)
n'est pas un `read`. Le processus MCP n'est pas soumis aux permissions
agent. Le film le dit sur la ligne, sinon on enseigne le contraire de
`docs/harness.md`.

## Hors scope

- Écrire `NOTES.md` à la place de l'agent.
- Modifier les deny rules, les agents, ou `kilo.jsonc`.
- Appeler Sidonie ou Albert autrement qu'en relais transparent.
- Index vectoriel, evals, auto-écriture de skills.
- Panneau VS Code, webview, extension.
- Piloter la compaction. La détecter, oui.
- Fork qui rappelle le modèle (le time-travel de Rewind). Le rejeu est
  lecture seule.
- Graphiques au premier jet, sauf une barre de tokens cumulés.
- Importer Langfuse, Phoenix, Helicone, Docker.

## Architecture

```
Kilo (VS Code), workspace = dossier d'affaire
  base URL → http://127.0.0.1:8765/v1
                │
                ▼
         pellicule proxy  ── écrit sessions/<id>/events.jsonl
                │
                ▼
         Sidonie ou Albert

À côté, dans le même process :
  config loader   kilo.jsonc fusionné + agents/*.md (provenance)
                  + kilo.base.jsonc si le fusionné manque
  log tail        tasks/<id>/api_conversation_history.json
                  et ui_messages.json si lisible
  case watcher    dossier d'affaire (pas le dépôt agent-lab)
  replay reader   un jsonl déjà écrit

UI statique  http://127.0.0.1:8766
  SSE /events pour le live
  GET /sessions et /sessions/{id} pour le rejeu
```

Le proxy est à nous, pas vLLora. vLLora reste un repli manuel si le proxy
casse le streaming. Le format d'événement ne dépend pas de vLLora.

Stack imposée, pour coller à Agent Lab et à Cursor : Python 3.11+, FastAPI,
une page HTML/CSS/JS sans framework, JSONL pour la trace. SQLite optionnel
plus tard pour lister les sessions, pas au jet 1. Pas de Docker. Windows
natif : le watcher et les chemins Kilo marchent sans WSL.

Deux ports pour que Kilo et le navigateur ne se marchent pas dessus.
`8765` est le relais. `8766` est la page. Un seul binaire les tient.

## Config chargée

Ordre de lecture, sans planter si un fichier manque.

1. Fichier fusionné écrit par `detect_kilo.py --apply`. Chemins à sonder :
   - `%USERPROFILE%\.config\kilo\kilo.jsonc`
   - `%USERPROFILE%\.kilo\kilo.jsonc`
   - `%USERPROFILE%\.kilocode\kilo.jsonc`
   - `%APPDATA%\Code\User\globalStorage\kilocode.kilo-code\` (settings)
   - le même sous `Code - Insiders` et le variant réellement utilisé
   - `kilo.jsonc` et `.kilo/kilo.jsonc` du workspace ouvert, s'il y en a un
2. Provenance : `agents/*.md` du dépôt Agent Lab (`AGENT_LAB_HOME`, sinon
   le clone connu). Frontmatter YAML, pas le corps.
3. Repli pédagogique : `config/kilo.base.jsonc` du dépôt. Marqué
   `config_source: base`, jamais présenté comme ce que Kilo a appliqué.

Précédence Kilo, du plus faible au plus fort, documentée dans l'UI à côté
du verdict :

1. Défauts natifs
2. Global `~/.config/kilo/kilo.jsonc`
3. `kilo.jsonc` à la racine du projet
4. `.kilo/` et l'ancien `.kilocode/`, agents Markdown
5. `KILO_CONFIG_CONTENT`

Agent Lab ne s'appuie pas sur la découverte automatique de `agents/*.md`
dans l'affaire. L'affaire est un autre dossier. `--apply` injecte le bloc
`agent` dans la config utilisateur. Le chargeur doit donc lire ce bloc
injecté. S'il ne le trouve pas, il le dit, et il recalcule quand même sur
les Markdown pour que le film existe. `agree` reste faux tant que la source
appliquée n'est pas lue.

Dialecte. `detect_kilo.py` tranche v7 (`permission`) contre l'extension
héritée (`customModes`, `fileRegex` sur l'écriture seulement). Le verrou
« ne pas lire un PDF de `sources/` » n'existe pas dans le dialecte hérité.
L'événement `policy` porte `dialect: v7 | legacy`. Sur legacy, un deny de
lecture absent n'est pas une divergence de précédence : c'est une limite du
dialecte, affichée comme telle.

`.kilocodeignore` converti en deny par Kilo est une couche possible. Si le
fichier existe, le chargeur le note. Il ne réimplémente pas l'IgnoreMigrator
au jet 1. S'il voit un deny dans le log que sa config ne contient pas, c'est
un `agree: false` avec hypothèse « règle hors config chargée ».

## Mode actif

Kilo ne l'envoie pas dans un header. Le sélecteur ou une commande `/` le
choisit. Le corps Markdown devient le system prompt. Le nom vient du
fichier.

Le modèle ne suffit pas. `plan` et `qa` partagent
`sidonie/{{MODEL_QWEN_THINK}}`. `ingest` et `deliver` partagent le Flash.
`vision` peut être `sidonie/…` ou `albert/…` déjà qualifié.

Live, dans cet ordre. Aucune phrase d'Agent Lab n'est codée en dur.
L'empreinte compare le system prompt au corps des agents chargés depuis
la config (frontmatter + markdown). Si le corps chargé est celui de
`plan.md`, le mode est `plan`. Ça marche sur un autre projet sans retouche.

1. Recouvrement du system prompt avec le corps d'un agent chargé.
   Confiance `likely`. Égalité ou absence de corps : `unknown`.
2. Commande `/` si le message user commence par un nom présent dans le
   bloc `command` de la config chargée. Confiance `likely`.
3. Confirmation par le JSON de tâche, champ agent ou mode s'il existe.
   Confiance `exact` si ça concorde, `contradicted` sinon.

Tant que ce n'est pas `exact`, le verdict policy est provisoire, badge
gris, pas rouge. Rouge seulement pour `agree: false` sur une règle, à
confiance exacte ou sur le log seul.

`default_agent` est lu dans la config. Chez Agent Lab il vaut `plan`.
Ailleurs, c'est ce que le fichier dit.

## Entêtement

Une deny n'est un succès de harness que si le modèle s'arrête. S'il
redemande le même outil sur le même motif, le verrou tient mais le tour
est brûlé. C'est la mesure que l'optimisation veut voir sans graphique.

Règle, calculée au rendu, pas codée pour un outil précis :

- Même `tool` + même motif normalisé (chemin relatif, ou nom d'agent
  `task`, ou premier segment bash) après un `deny` ou un `ask` rejeté.
- Fenêtre : le reste de la session, pas seulement le tour suivant.
- À partir de la deuxième tentative : badge `réessai` sur la ligne, compteur
  sur la première deny, tokens de completion des tours intermédiaires
  additionnés dans le détail.
- La première deny reste ambre. Les réessais passent ambre souligné, pour
  ne pas les confondre avec `agree: false`.

Le jsonl ne duplique pas l'événement. Il porte `retry_of` (le
`tool_call_id` de la deny d'origine) et `retry_index` sur le
`tool_request` suivant. L'UI groupe. Un collègue lit « le modèle a
redemandé trois fois un PDF refusé », pas trois lignes isolées.

## Policy

Reprendre le dialecte Kilo, pas l'inventer. Aucune règle métier dans le
binaire. `sources/**/*.pdf`, `vision`, `analysis/` ne sont pas des
constantes Python. Ce sont des lignes lues. Un autre projet pose ses
fichiers dans le chargeur et obtient le même film.

Le chargeur accepte :

- frontmatter YAML d'agents (`permission:` sous `---`) ;
- `kilo.jsonc` / `kilo.json` (commentaire JSONC toléré, clé `permission`
  et bloc `agent.<nom>.permission`) ;
- un fichier de règles générique plus tard, même schéma d'actions, si un
  autre harness documente last-match-wins. Pas au jet 1 au-delà de Kilo.

Le scénario d'acceptation pointe un dossier de fixtures copié depuis
Agent Lab. Si on remplace les fixtures, les cinq denies attendues
changent. Le test vérifie que le moteur a lu le fichier, pas qu'il
connaît Agent Lab.

## Événement

Un seul schéma. Le live et le rejeu lisent la même chose.

```json
{
  "ts": "2026-10-03T11:00:00.000Z",
  "session_id": "uuid",
  "parent_session_id": null,
  "case_dir": "C:/affaires/carte-ep",
  "turn": 3,
  "layer": "policy",
  "tool_call_id": "call_abc",
  "mode": "plan",
  "mode_confidence": "exact",
  "model": "sidonie/qwen",
  "summary": "deny read sources/note.pdf",
  "latency_ms": null,
  "prompt_tokens": null,
  "completion_tokens": null,
  "detail": {
    "tool": "read",
    "path": "sources/note.pdf",
    "verdict": "deny",
    "ask_state": null,
    "matched_rule": "read: deny sources/**/*.pdf",
    "rule_source": "agents/plan.md",
    "config_source": "merged",
    "dialect": "v7",
    "precedence": "last-match-wins",
    "losers": [
      "read: allow *"
    ],
    "kilo_log": "permission denied: read sources/note.pdf",
    "agree": true,
    "hypothesis": null,
    "retry_of": null,
    "retry_index": 0
  }
}
```

Champs stables, dès le jet 1, pour ne pas refaire une passe :

- `latency_ms`, `prompt_tokens`, `completion_tokens` sur `llm`. Null si le
  provider ne les envoie pas. Ne pas inventer un pourcentage de fenêtre.
  L'afficher comme « inconnu », avec le cumul quand même.
- `verdict` sur `policy` : `allow`, `deny`, `ask`.
- `ask_state` : `pending`, `approved`, `rejected_by_user`, ou null.
- `losers` : règles qui ont matché et n'ont pas gagné, dans l'ordre.
- `config_source` : `merged`, `agents_md`, `base`.
- `dialect` : `v7` ou `legacy`.
- `mode_confidence` : `exact`, `likely`, `unknown`, `contradicted`.
- `parent_session_id` pour un `task` autorisé.
- `case_dir` pour relier plusieurs sessions à une affaire.
- `retry_of` et `retry_index` sur un `tool_request` qui répète un deny.

`hypothesis` est rempli seulement si `agree` est faux. Valeurs prévues :
`precedence`, `rule_not_in_loaded_config`, `dialect_legacy`,
`mode_unknown`, `log_unparsed`.

Tokens : ne pas inventer un pourcentage de fenêtre si `/v1/models` ne
déclare pas de contexte. Le premier POST réel tranche si Sidonie ou Albert
renvoient `usage`. Jusque-là, le champ reste null.

Raisonnement : `reasoning` et `reasoning_content` sont relayés sans être
interprétés. Ils vont dans un pli du détail `llm`, séparés de la réponse
visible. Pas de schéma plus fin avant un payload réel.

## Policy

Reprendre le dialecte Kilo, pas l'inventer.

- Actions : `allow`, `ask`, `deny`.
- Une règle peut être globale (`read: deny`) ou une table de globs.
- Dernière règle qui matche gagne. Le documenter dans l'UI, à côté du
  verdict, avec la liste des perdants.
- Outils fichier : résoudre le chemin, puis matcher le chemin relatif au
  workspace. Le workspace est l'affaire, pas le dépôt.
- `bash` : Kilo découpe la commande. Un seul segment interdit refuse toute
  la commande. `cd` plus `git` peut être deny sur le second segment.
  `external_directory` est un motif possible, affiché s'il apparaît dans le
  log, pas deviné.
- `task` : le nom d'agent est le motif. Clés sans guillemets dans le
  frontmatter Agent Lab (`ingest: allow`) et clés étoilées (`"*": deny`).
- Fichiers sensibles : Kilo force un ask sur `.env` même si `*` est allow.
  `.env.example` est considéré sain. Le moteur le note comme règle
  intégrée, pas comme une ligne de `agents/*.md`.
- MCP : pas de verdict fichier. Un outil dont le nom figure dans le bloc
  `mcp` chargé, ou qui n'a pas de clé dans `permission`, est annoté
  « hors table de permissions agent ». On n'écrit pas `doc_*` dans le
  binaire. Le préfixe est celui de la config.

Règles Agent Lab à couvrir dès le premier scénario, lues depuis la config,
pas codées en dur. État lu dans le dépôt au 2026-10-03 :

- `read: deny` sur `sources/**/*.pdf`, Office, `*.pst`. Images
  (`png`, `jpg`, `jpeg`, `webp`, `gif`, `tif`, `tiff`, `bmp`) refusées à
  `plan`, `ingest`, `deliver`, `qa`, après `*`, parce que la dernière
  règle gagne. `vision` n'a pas ce refus : son `*` rouvre la lecture.
- `edit` : `plan` n'écrit que `NOTES.md`, `AGENTS.md`, `output/**/*.md`.
  `ingest` n'écrit que `extracts/**/*.md` et `extracts/**/*.json`.
  `qa` et `vision` : `edit: *` deny. Global base : `**/*.py` ask, sauf
  `analysis/**/*.py` allow, `sources/**` deny.
- bash allowlist : motifs `*agent-lab*` sur `extract.py`, `write_office.py`,
  `case_lint.py`, `check_citations.py`, `stage_image.py`, `render_pages.py`,
  `wiki.py`, `mail.py`, plus `python analysis/*`. `python -c`, `pip`,
  `powershell`, `cmd`, `pandoc` deny. Le reste ask au global. `plan`, `qa`
  et `vision` ont `bash: *` deny dans leur frontmatter.
- `task` vers `vision`, `general`, `code`, `explore` refusé. `plan` peut
  déléguer à `ingest`, `deliver`, `qa`. `qa` et `vision` ont `task: deny`.
- `ingest` ne peut bash que `*agent-lab*extract.py*`.

Si la config fusionnée dit autre chose, la config gagne. Le scénario échoue
alors de façon visible, il ne ment pas.

Matchers. Globs Kilo, pas une réinvention. `**` traverse les dossiers.
L'ordre du fichier est l'ordre d'évaluation, pas la spécificité. Une règle
plus spécifique placée avant un `*` perd. C'est le bug pédagogique n°1, il
doit être visible sans lire le YAML.

## Logs Kilo

Chemins Windows à sonder, dans cet ordre, sans planter si absents :

- `%APPDATA%\Code\User\globalStorage\kilocode.kilo-code\tasks\<id>\api_conversation_history.json`
- le même dossier, `ui_messages.json` (peut être verrouillé ; ne pas bloquer)
- le même sous `Code - Insiders` ou le variant réellement utilisé
- logs CLI `~/.kilocode/cli/logs/` si présents
- canal Output « Kilo Code » : souvent pas un fichier. Ne pas bloquer le
  dashboard dessus. Le fichier de tâche est la source stable.

Le workspace ouvert est l'affaire. L'id de tâche n'est pas dans le POST.
Le tail suit le dossier `tasks/` le plus récemment modifié pendant la
session, et le lie par horodatage plus nom d'outil. Si deux tâches bougent,
on les affiche toutes les deux avec un badge d'ambiguïté, on n'en choisit
pas une en silence.

Parser défensif. Un format inconnu devient un événement `kilo_log` brut,
pas une exception. On ne suppose pas que le message de deny contient le nom
de la règle.

## Watcher d'affaire

Surveille le dossier ouvert par Kilo, pas le dépôt `agent-lab`. Layout
attendu, informatif, pas bloquant :

```
sources/     originaux
extracts/    markdown produit
output/      livrables
analysis/    calcul
NOTES.md
AGENTS.md
```

Événement `case_write` : chemin relatif, création ou modification, taille,
horodatage. Pas le contenu. Si le chemin matche une règle `edit: deny`
chargée, la ligne est annotée « écriture que la config interdisait ».
Pas de liste en dur de dossiers `analysis/` ou d'extensions `.py`.

Ignorés, pour ne pas polluer le film :

- suffixes et noms : `.tmp`, `.temp`, `.lock`, `.swp`, `.swo`, `~`,
  `desktop.ini`, `Thumbs.db`, `.DS_Store` ;
- dossiers : `.git/`, `__pycache__/`, `.pytest_cache/`, `node_modules/`,
  `.venv/`, `*.lock` laissé par un outil ;
- fichiers dont l'écriture dure moins que le tick du watcher et qui
  disparaissent (lock éphémère).

Le filtre est une liste dans la config Pellicule, pas dans le code métier.
Un projet peut la rallonger. Le défaut ci-dessus suffit pour une affaire
documentaire Windows.

Une affaire est traitée par plusieurs sessions. `case_dir` est un tag.
La clé de rejeu reste `session_id` (une conversation Kilo).

## Film imbriqué et commandes `/`

- `task` allow (`ingest`, `deliver`, `qa` depuis `plan`) : session fille,
  `parent_session_id` rempli, film indenté, lien vers le parent.
- `task` deny (`vision`, `general`, `code`, `explore`) : une ligne policy.
  Pas de film vide.
- `/ingest`, `/qa`, `/vision`, `/deliver`, `/intake` : même session.
  Événement `mode`. Le commentaire de `kilo.base.jsonc` interdit
  `subtask: true` parce que l'invite de permission du fils ne s'affiche
  pas dans VS Code. Enseigner une boîte imbriquée ici serait faux.

## Proxy

OpenAI-compatible, relais transparent.

- `POST /v1/chat/completions`, stream et non-stream.
- `GET /v1/models` relais, pour voir si une fenêtre est déclarée. Le résultat
  est un événement `models` une fois par session, pas à chaque tour.
- Clé upstream dans un fichier local ignoré par git (`pellicule.keys`, à
  côté des sessions, pas dans Agent Lab). Jamais dans le dépôt.
- Deux upstreams nommés, Sidonie et Albert, choisis par le modèle préfixé
  (`sidonie/…`, `albert/…`) ou par un header. Ne pas casser un ID déjà
  qualifié. Ne pas préfixer une seconde fois.
- Streaming : relayer les chunks SSE sans les bufferiser jusqu'à la fin.
  L'événement `llm` est clos à la fin du stream. Les tool calls peuvent
  arriver en deltas : on assemble, on n'émet `tool_request` qu'une fois le
  call complet.
- Champs inconnus (`reasoning`, `reasoning_content`, `stream_options`,
  cache) : relais byte à byte. On ne les schématise pas avant un payload.
- Panne upstream : événement `llm` en erreur, Kilo reçoit l'erreur telle
  quelle.

Kilo pointe sa base URL custom vers `http://127.0.0.1:8765/v1`.
Une seule instance Kilo. Un second VS Code sur le même port est hors
spec : le proxy refuse la seconde base URL concurrente avec un événement
`llm` d'erreur, il ne mélange pas les sessions.

## Rétention

Une session écrit `sessions/<id>/events.jsonl` plus un `meta.json`
(workspace, `case_dir`, mode de départ, upstream, début, fin, dialecte,
`config_source`).

Corps des messages et des tool results : hash SHA-256, taille en octets,
2 Ko de tête. Corps complet si le tour contient un deny, un ask, ou une
compaction. Les extraits PDF et les PNG base64 ne doivent pas rendre le
jsonl illisible dans Cursor.

`meta.json` porte la liste des fichiers de config lus et leur mtime, pour
savoir plus tard si la règle a changé entre deux sessions.

## UI

Une page statique, HTML/CSS/JS sans framework, servie par FastAPI sur
`http://127.0.0.1:8766`. Trois zones. Le nom du layer et sa légende sont
toujours visibles. Public : l'auteur et un collègue qui n'a pas écrit les
règles.

Direction visuelle : densité Linear, sombre, pas un HUD de film
d'ingénierie. Linear gagne parce que le cours est dans le texte de la
ligne (règle, perdants, accord). Un HUD (grilles, scanlines, bords
lumineux sur chaque carte, labels en capitales partout) concurrence les
quatre couleurs d'état, qui sont déjà le signal. On garde le calme de
Linear et la monospace pour les chemins. On ne garde pas le décor.

- Fond `#0d0f12`, surface `#16181d`, filet `1px` `#2a2e36`. Pas de lueur.
- Texte : une sans pour les légendes (lisible à voix haute devant un
  collègue), une monospace pour chemins, règles, `tool_call_id`.
  Pile : `ui-sans-serif` puis `JetBrains Mono`, `ui-monospace`. Pas de
  webfont téléchargée : rien ne sort, et le poste peut être hors ligne.
  Si une police locale existe, elle s'applique. Sinon le fallback système.
- Deny harness : ambre `#e0a106`. Succès du verrou.
- Réessai après deny : même ambre, souligné, badge `réessai × N`.
- Erreur modèle ou outil : rouge `#f0514a`.
- `agree: false` : le même rouge, même si le verdict est deny.
- Ask en attente : bleu `#5b8def`.
- Compaction : violet `#b07cff`.
- Changement de mode : filet neutre, pas une cinquième couleur criarde.
- Écriture qui matche un `edit: deny` : ambre pointillé.

Zones :

1. Film du tour, vertical. Chaque événement est une ligne : heure, layer,
   légende courte, résumé. Fille indentée. Barre de trajectoire mince
   au-dessus (idée cctrace) : un bloc par tour, cliquable. Les réessais
   s'y voient comme une répétition du même bloc ambre, pas comme un
   nouveau type d'événement. Pas de camembert, pas de Grafana.
2. Détail. Pour un deny ou un ask : outil, chemin, règle gagnante, règles
   perdantes, fichier source, `config_source`, dialecte, précédence, texte
   Kilo, accord config/log, hypothèse si désaccord, compteur de réessais
   et tokens brûlés. Pour un appel LLM : rôle des messages et taille en
   tokens, ouvert par défaut. Dump brut derrière un pli. Raisonnement
   derrière un autre pli.
3. Session. Liste des sessions enregistrées par Pellicule, groupables par
   `case_dir`. Bouton rejouer. Le rejeu est le même film, horloge
   d'origine, aucun POST upstream. Pas d'import d'un historique Kilo
   d'avant le proxy.

Barre de tokens cumulés, avec « fenêtre inconnue » si le modèle ne la
déclare pas. Le cumul des réessais est une ligne sous la barre, pas un
second graphe. Pas d'autre graphique au jet 1.

## Rejeu

Rejouer ne relit que les `events.jsonl` que Pellicule a écrits. Pas de
réseau. Pas de reconstruction de l'historique Kilo antérieur : les tâches
déjà sur le disque avant le lancement du proxy ne sont pas un film.
Utile pour ouvrir le film dans Cursor plus tard : le jsonl est la pièce
à joindre au chat, pas une capture d'écran. Le rejeu ne rappelle pas le
modèle, ne réexécute pas les outils, ne réécrit pas l'affaire.

## Scénario d'acceptation

Fixtures copiées depuis Agent Lab, lues par le chargeur. Le binaire ne
contient pas ces globs. Affaire jouet : un PDF deux pages, un PNG, un
`.py` hors le dossier que la fixture autorise. Compaction auto laissée
telle quelle. Ne pas la piloter.

Le dashboard est accepté s'il montre, sur un rejeu de son propre jsonl :

1. Un tool présent dans le bloc `mcp` de la fixture : llm, tool_request,
   policy allow annotée « hors table de permissions agent », exec, fichier
   d'affaire, second llm. Le deny de lecture du PDF n'est pas confondu
   avec cet allow.
2. Cinq refus, chacun avec la règle gagnante, les perdants, et `agree`
   vrai ou expliqué. Les motifs viennent des fixtures, pas du code :
   lecture d'un binaire refusé, écriture hors zone autorisée, bash hors
   allowlist, `task` vers un agent refusé, agent lecture seule qui écrit.
3. Un `ask`, quatre états visibles si l'utilisateur répond.
4. Une suite dans la même session avec changement de mode (`/` lu dans
   le bloc `command`), plusieurs `tool_call_id`. Pas un film imbriqué.
5. Un `task` allow, film indenté, si la délégation a lieu. Pas obligatoire
   pour accepter le jet 1 si le scénario 2 est complet.
6. Un réessai : le même outil, le même motif, après une deny. Badge
   `réessai`, tokens des tours intermédiaires dans le détail.
7. Une compaction si elle survient : événement `compact`, tour suivant plus
   court, aperçu de ce qui a été élagué. Pas obligatoire pour le jet 1.
8. Un fichier `.tmp` ou un lock dans l'affaire n'apparaît pas dans le film.

## Ordre de vibe coding

1. Proxy qui enregistre et relais, plus la page qui liste les `llm` avec
   la légende. Streaming non bufferisé. Page sombre, sans décor.
2. Extraction des tool calls et des messages `tool`.
3. Chargeur de config générique et moteur last-match-wins, branché sur
   les fixtures. Premier écran utile : un deny complet, avec perdants.
4. `ask` et ses quatre états. Badge `réessai` sur la deuxième deny identique.
5. Watcher de dossier d'affaire, filtre temporaires.
6. Lecteur du JSON de tâche Kilo, champ `agree`, hypothèse si faux.
7. Empreinte de mode par recouvrement du corps chargé, badge de confiance.
8. Événement `mode` pour les commandes lues dans la config.
9. Film imbriqué pour `task` allow.
10. Rejeu des seuls jsonl Pellicule. Rétention hash + tête, corps complet
    sur deny / ask / compact.

Ne pas commencer par l'UI décorée. Ne pas commencer par l'imbrication.
Le film d'un deny complet, avec perdants et légende, est le premier écran
utile. Aucune constante `sources/` ou `vision` dans ce chemin.

## Critère de fin

Sur le scénario 2, l'écran montre la règle, les règles qui ont perdu, le
fichier de config, le texte Kilo, et si les deux sont d'accord. Une légende
fixe dit que Kilo a tranché, pas le modèle. Un réessai du même deny est
groupé, avec les tokens brûlés. La trace reste sur la machine. Le jsonl
s'ouvre dans Cursor sans rappeler le modèle. Un collègue qui n'a pas écrit
les règles comprend pourquoi le fichier n'a pas été lu, et pourquoi l'outil
MCP a quand même eu lieu. Remplacer les fixtures par un autre projet ne
demande pas de patcher le binaire.

## Décisions de cadrage, 2026-10-04

Tranchées. Plus des questions ouvertes.

1. Vérité = `kilo.jsonc` fusionné. Provenance affichée = agents Markdown.
   Si le fusionné est introuvable, repli Markdown + badge `config_source:
   agents_md`, et `agree` faux.
2. Premier écran = deny complet avec perdants, avant le film imbriqué.
3. Corps complet seulement sur deny, ask, compaction. Sinon 2 Ko.
4. Fenêtre de contexte : inconnue tant que `/v1/models` ne la donne pas.
5. Deux tâches Kilo qui bougent en même temps : on affiche les deux.
6. Rejeu = jsonl Pellicule seulement. Pas d'historique Kilo antérieur.
7. Une instance Kilo. Pas de multiplexage sur 8765.
8. Entêtement visible dès le deuxième réessai du même motif refusé.
9. Watcher sans `.tmp`, locks, caches. Liste rallongeable, pas en dur métier.
10. Zéro règle Agent Lab dans le binaire. Les fixtures portent le scénario.
11. IHM Linear sombre, pas HUD. Couleurs d'état strictes, pas de lueur.
