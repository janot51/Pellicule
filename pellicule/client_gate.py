from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class GateDecision:
    allowed: bool
    reason: str | None = None


class ClientGate:
    """Une seule session cliente active (pas de multiplexage au jet 1)."""

    def __init__(self) -> None:
        self._holder: str | None = None
        self._lock = asyncio.Lock()

    def client_token(
        self,
        authorization: str | None,
        remote: str | None,
        user_agent: str | None = None,
        client_id: str | None = None,
    ) -> str:
        if client_id:
            return f"client:{client_id[:64]}"
        if authorization:
            return f"auth:{authorization[:64]}"
        if user_agent:
            return f"ua:{user_agent[:120]}"
        if remote:
            return f"peer:{remote}"
        return "anonymous"

    async def try_acquire(self, token: str) -> GateDecision:
        async with self._lock:
            if self._holder is None:
                self._holder = token
                return GateDecision(allowed=True)
            if self._holder == token:
                return GateDecision(allowed=True)
            return GateDecision(
                allowed=False,
                reason="Un autre client utilise déjà le proxy Pellicule sur ce port.",
            )
