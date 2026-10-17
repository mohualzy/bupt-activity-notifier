"""Chrome/Edge Native Messaging host; stdin/stdout are a binary JSON pipe.

Windows Edge starts the small EXE launcher beside this file. The EXE forwards
the native message to this process without printing credentials or opening a
local web server. Only dekt.bupt.edu.cn may supply a candidate via the extension.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys

PROJECT = Path(__file__).resolve().parents[1]
EXTENSION_ID = "mcohcjkicfoblidoolgbpladhehllpbb"
ALLOWED_ORIGIN = "chrome-extension://" + EXTENSION_ID + "/"
MAX_INPUT_BYTES = 12 * 1024
MAX_OUTPUT_BYTES = 4096


def _framed_read(stream) -> dict | None:
    prefix = stream.read(4)
    if len(prefix) != 4:
        return None
    (size,) = struct.unpack("<I", prefix)
    if size > MAX_INPUT_BYTES or size <= 0:
        return None
    raw = stream.read(size)
    if len(raw) != size:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _framed_write(stream, status: str) -> None:
    if not isinstance(status, str) or not status.isascii() or not status.replace("_", "").islower():
        status = "native_host_error"
    data = json.dumps({"status": status}, separators=(",", ":")).encode("ascii")
    if len(data) > MAX_OUTPUT_BYTES:
        data = b'{"status":"native_host_error"}'
    stream.write(struct.pack("<I", len(data)) + data)
    stream.flush()


def handle(message: dict | None, *, origin: str, root: Path = PROJECT) -> str:
    if origin != ALLOWED_ORIGIN:
        return "invalid_origin"
    if not isinstance(message, dict):
        return "invalid_message"
    if message.get("kind") == "ping":
        return "ready"
    if message.get("kind") != "sync":
        return "invalid_message"
    token = message.get("jwt")
    if not isinstance(token, str):
        return "invalid_candidate"
    sys.path.insert(0, str(root / "src"))
    from bupt_activity_notifier.edge_token_sync import sync_candidate

    return sync_candidate(token, root)


def main() -> int:
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    origin = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        message = _framed_read(sys.stdin.buffer)
        status = handle(message, origin=origin)
    except Exception:
        status = "native_host_error"
    _framed_write(sys.stdout.buffer, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
