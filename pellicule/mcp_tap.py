from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pellicule.settings import data_root


def _read_frame(stream: Any) -> bytes | None:
    header = b""
    while not header.endswith(b"\r\n\r\n"):
        chunk = stream.read(1)
        if not chunk:
            return None
        header += chunk
    lines = header.decode("ascii", errors="replace").split("\r\n")
    length = 0
    for line in lines:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length <= 0:
        return None
    body = stream.read(length)
    if len(body) != length:
        return None
    return body


def _write_frame(stream: Any, payload: bytes) -> None:
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    stream.write(header)
    stream.write(payload)
    stream.flush()


def _active_session_id() -> str | None:
    path = data_root() / "active_session.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sid = data.get("session_id")
    return str(sid) if sid else None


def _post_ingest(url: str, direction: str, payload: bytes) -> None:
    frame_text = None
    parse_error = False
    try:
        frame_text = payload.decode("utf-8")
        json.loads(frame_text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        parse_error = True
    body = {
        "session_id": _active_session_id(),
        "direction": direction,
        "frame_text": frame_text,
        "parse_error": parse_error,
        "size_bytes": len(payload),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, TimeoutError):
        pass


def _relay_stream(
    source: Any,
    dest: Any,
    ingest_url: str,
    direction: str,
) -> None:
    """Relais transparent : MCP stdio = JSON + saut de ligne (SDK MCP 2.x)."""
    while True:
        line = source.readline()
        if not line:
            break
        dest.write(line)
        dest.flush()
        stripped = line.strip()
        if stripped:
            _post_ingest(ingest_url, direction, stripped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pellicule mcp-tap")
    parser.add_argument(
        "--ingest",
        default="http://127.0.0.1:8766/ingest",
        help="URL POST /ingest",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Commande après --")
    args = parser.parse_args(argv)
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("commande serveur MCP requise après --")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    import threading

    def stderr_copy() -> None:
        while True:
            chunk = proc.stderr.read(4096)
            if not chunk:
                break
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()

    threading.Thread(target=stderr_copy, daemon=True).start()
    threading.Thread(
        target=_relay_stream,
        args=(sys.stdin.buffer, proc.stdin, args.ingest, "client"),
        daemon=True,
    ).start()
    _relay_stream(proc.stdout, sys.stdout.buffer, args.ingest, "server")
    proc.wait()
    return proc.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
