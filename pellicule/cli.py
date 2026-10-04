from __future__ import annotations

import argparse

from pellicule.run import main as run_main
from pellicule.settings import PROXY_PORT, UI_PORT


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pellicule",
        description="Proxy OpenAI Pellicule + film des événements",
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        default=PROXY_PORT,
        help=f"Port du proxy (défaut {PROXY_PORT})",
    )
    parser.add_argument(
        "--ui-port",
        type=int,
        default=UI_PORT,
        help=f"Port de l'interface (défaut {UI_PORT})",
    )
    args = parser.parse_args()
    if args.proxy_port != PROXY_PORT or args.ui_port != UI_PORT:
        import pellicule.settings as settings

        settings.PROXY_PORT = args.proxy_port
        settings.UI_PORT = args.ui_port
    run_main()
