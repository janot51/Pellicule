from __future__ import annotations

import hashlib
from typing import Any

HEAD_MAX_BYTES = 2048


def retain_text_body(content: Any, *, full: bool = False) -> dict[str, Any]:
    if content is None:
        data = b""
    elif isinstance(content, bytes):
        data = content
    elif isinstance(content, str):
        data = content.encode("utf-8")
    else:
        data = str(content).encode("utf-8")
    head = data[:HEAD_MAX_BYTES].decode("utf-8", errors="replace")
    out: dict[str, Any] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "head": head,
    }
    if full:
        out["full"] = data.decode("utf-8", errors="replace")
    return out


def retain_for_policy_verdict(verdict: str | None, content: Any) -> dict[str, Any]:
    full = verdict in ("deny", "ask")
    return retain_text_body(content, full=full)
