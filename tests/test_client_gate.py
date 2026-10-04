import asyncio

from pellicule.client_gate import ClientGate


def test_gate_single_holder() -> None:
    async def run() -> None:
        gate = ClientGate()
        assert (await gate.try_acquire("a")).allowed
        assert (await gate.try_acquire("a")).allowed
        denied = await gate.try_acquire("b")
        assert not denied.allowed
        assert denied.reason

    asyncio.run(run())
