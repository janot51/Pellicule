from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def tool_message_indicates_rejection(content: Any) -> bool:
    if content is None:
        return False
    if isinstance(content, dict):
        if content.get("isError") is True or content.get("error"):
            return True
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    lower = text.lower()
    hints = (
        "rejected by user",
        "user rejected",
        "user declined",
        "user denied",
        "denied by user",
        "not approved",
        "approval denied",
        "cancelled by user",
        "canceled by user",
        "permission denied",
        "ask rejected",
    )
    return any(h in lower for h in hints)


@dataclass
class PendingAsk:
    tool_call_id: str
    tool: str
    motif: str
    mode: str
    base_detail: dict[str, Any]


@dataclass
class AskStateTracker:
    pending: dict[str, PendingAsk] = field(default_factory=dict)

    def register_pending(
        self,
        tool_call_id: str,
        tool: str,
        motif: str,
        mode: str,
        policy_detail: dict[str, Any],
    ) -> None:
        self.pending[tool_call_id] = PendingAsk(
            tool_call_id=tool_call_id,
            tool=tool,
            motif=motif,
            mode=mode,
            base_detail=dict(policy_detail),
        )

    def resolve(
        self,
        tool_call_id: str,
        content: Any,
    ) -> tuple[PendingAsk, str] | None:
        pending = self.pending.pop(tool_call_id, None)
        if pending is None:
            return None
        if tool_message_indicates_rejection(content):
            return pending, "rejected_by_user"
        return pending, "approved"
