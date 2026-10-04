"""Métadonnées d'affichage par layer (schéma stable, sans règles métier)."""

LAYER_META: dict[str, dict[str, str]] = {
    "llm": {
        "legend_fr": "Le modèle a reçu ce contexte et a répondu.",
    },
    "models": {
        "legend_fr": "Liste des modèles déclarés par l'upstream.",
    },
    "tool_request": {
        "legend_fr": "Le modèle a demandé un outil. Ce n'est pas encore une action.",
    },
    "exec": {
        "legend_fr": "L'outil a tourné, ou le harness l'a arrêté.",
    },
    "policy": {
        "legend_fr": "Kilo a tranché avant d'exécuter. La dernière règle qui matche gagne.",
    },
    "case_write": {
        "legend_fr": "Le dossier d'affaire a bougé. Seule preuve hors du modèle.",
    },
    "mode": {
        "legend_fr": "Ce n'est pas un sous-agent. La commande ou l'invite a changé les droits.",
    },
    "kilo_log": {
        "legend_fr": "Source Kilo non comprise. On ne l'invente pas.",
    },
    "compact": {
        "legend_fr": "Le contexte a été résumé. Ce qui n'était pas dans NOTES.md est perdu.",
    },
}


def legend_for(layer: str) -> str:
    meta = LAYER_META.get(layer)
    if meta:
        return meta["legend_fr"]
    return ""
