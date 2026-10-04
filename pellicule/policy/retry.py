from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BlockRecord:
    tool_call_id: str
    tool: str
    motif: str
    verdict: str
    retry_count: int = 0


@dataclass
class RetryTracker:
    blocks: list[BlockRecord] = field(default_factory=list)
    _completion_buffer: int = 0

    def add_completion_tokens(self, tokens: int | None) -> None:
        if tokens and tokens > 0:
            self._completion_buffer += int(tokens)

    def register_block(self, tool_call_id: str, tool: str, motif: str, verdict: str) -> None:
        if verdict not in ("deny", "ask"):
            return
        self.blocks.append(
            BlockRecord(
                tool_call_id=tool_call_id,
                tool=tool,
                motif=motif,
                verdict=verdict,
            )
        )

    def register_ask_rejected(self, tool_call_id: str, tool: str, motif: str) -> None:
        self.register_block(tool_call_id, tool, motif, "ask")

    def check_retry(self, tool: str, motif: str) -> tuple[str | None, int, int]:
        """Retourne (retry_of, retry_index, burned_completion_tokens)."""
        for block in reversed(self.blocks):
            if block.tool != tool or block.motif != motif:
                continue
            if block.verdict not in ("deny", "ask"):
                continue
            block.retry_count += 1
            burned = self._completion_buffer
            self._completion_buffer = 0
            return block.tool_call_id, block.retry_count, burned
        return None, 0, 0
