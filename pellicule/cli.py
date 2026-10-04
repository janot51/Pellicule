from __future__ import annotations

import argparse
import sys

from pellicule.settings import PROXY_PORT, UI_PORT, bootstrap_config


def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--proxy-port",
        type=int,
        default=None,
        help=f"Port du proxy (défaut {PROXY_PORT})",
    )
    parser.add_argument(
        "--ui-port",
        type=int,
        default=None,
        help=f"Port de l'interface (défaut {UI_PORT})",
    )


def _run_serve(args: argparse.Namespace) -> int:
    bootstrap_config(proxy_port=args.proxy_port, ui_port=args.ui_port)
    from pellicule.run import main as run_main

    run_main()
    return 0


def _run_init(args: argparse.Namespace) -> int:
    from pellicule.init_cmd import run_init

    return run_init(
        force=args.force,
        data_dir=args.data_dir,
        case_dir=args.case_dir,
        workspace=args.workspace,
        merged_config=args.merged_config,
        agents_dir=args.agents_dir,
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
    )


def _run_doctor(_args: argparse.Namespace) -> int:
    bootstrap_config()
    from pellicule.doctor_cmd import run_doctor

    return run_doctor()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pellicule",
        description="Proxy OpenAI Pellicule + film des événements",
    )
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="Lancer le proxy et l'interface")
    _add_serve_args(serve_parser)

    init_parser = sub.add_parser("init", help="Créer pellicule.toml et pellicule.keys")
    init_parser.add_argument("--force", action="store_true", help="Écraser les fichiers existants")
    init_parser.add_argument("--data-dir", help="Répertoire de données (sessions, clés)")
    init_parser.add_argument("--case-dir", help="Dossier d'affaire surveillé")
    init_parser.add_argument("--workspace", help="Workspace pour la recherche config Kilo")
    init_parser.add_argument("--merged-config", help="Chemin kilo.jsonc fusionné")
    init_parser.add_argument("--agents-dir", help="Dossier agents/*.md")
    init_parser.add_argument("--provider", default="default", help="Section pellicule.keys")
    init_parser.add_argument("--base-url", default="https://votre-endpoint/v1")
    init_parser.add_argument("--api-key", default=None)

    sub.add_parser("doctor", help="Vérifier l'installation et la configuration")

    mcp_tap = sub.add_parser("mcp-tap", help="Relais MCP vers Pellicule /ingest")
    mcp_tap.add_argument(
        "--ingest",
        default="http://127.0.0.1:8766/ingest",
        help="URL POST /ingest",
    )
    mcp_tap.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Commande du serveur MCP (après --)",
    )

    _add_serve_args(parser)

    args = parser.parse_args(argv)
    command = args.command

    if command == "init":
        sys.exit(_run_init(args))
    if command == "doctor":
        sys.exit(_run_doctor(args))
    if command == "mcp-tap":
        from pellicule.mcp_tap import main as mcp_tap_main

        sys.exit(mcp_tap_main(["--ingest", args.ingest, *args.command]))
    if command in (None, "serve"):
        sys.exit(_run_serve(args))

    parser.print_help()
    sys.exit(2)
