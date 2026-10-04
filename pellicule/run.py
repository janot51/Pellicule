from __future__ import annotations

import asyncio
from typing import Any

import uvicorn

from pellicule.client_gate import ClientGate
from pellicule.hub import EventHub
from pellicule.policy import PolicyService, load_policy_config
from pellicule.proxy_app import create_proxy_app
from pellicule.session import SessionStore
from pellicule.keys import KeysError, provider_names
from pellicule.settings import (
    PROXY_HOST,
    PROXY_PORT,
    UI_HOST,
    UI_PORT,
    case_dir_from_env,
    data_root,
    sessions_dir,
)
from pellicule.ui_app import create_ui_app
from pellicule.kilo_tail import KiloTailCoordinator
from pellicule.watcher import WatcherCoordinator


def _print_startup_summary(policy_config) -> None:
    try:
        providers = ", ".join(provider_names()) or "(aucun)"
    except KeysError:
        providers = "(pellicule.keys manquant ou invalide)"
    print(
        f"Pellicule — proxy http://{PROXY_HOST}:{PROXY_PORT}/v1 "
        f"| UI http://{UI_HOST}:{UI_PORT}"
    )
    print(f"  données : {data_root()}")
    print(f"  upstream : {providers}")
    print(f"  policy : {policy_config.config_source}")
    case = case_dir_from_env()
    if case:
        print(f"  affaire : {case}")


async def serve() -> None:
    sessions_dir().mkdir(parents=True, exist_ok=True)
    hub = EventHub()
    store = SessionStore()
    gate = ClientGate()

    policy_config = load_policy_config()
    _print_startup_summary(policy_config)
    policy = PolicyService(policy_config)

    async def record_and_publish(event: dict[str, Any]) -> None:
        store.append_event(event)
        await hub.publish(event)

    watcher = WatcherCoordinator(store, policy, record_and_publish)
    kilo_tail = KiloTailCoordinator(store, policy_config, record_and_publish)
    env_case = case_dir_from_env()
    if env_case:
        await watcher.set_case_dir(env_case)

    proxy = create_proxy_app(store, hub, gate, policy, watcher, kilo_tail)
    ui = create_ui_app(hub)

    proxy_config = uvicorn.Config(
        proxy,
        host=PROXY_HOST,
        port=PROXY_PORT,
        log_level="info",
        access_log=False,
    )
    ui_config = uvicorn.Config(
        ui,
        host=UI_HOST,
        port=UI_PORT,
        log_level="info",
        access_log=False,
    )
    proxy_server = uvicorn.Server(proxy_config)
    ui_server = uvicorn.Server(ui_config)

    tail_task = asyncio.create_task(kilo_tail.run())
    try:
        await asyncio.gather(proxy_server.serve(), ui_server.serve())
    finally:
        kilo_tail.stop()
        tail_task.cancel()


def main() -> None:
    asyncio.run(serve())
