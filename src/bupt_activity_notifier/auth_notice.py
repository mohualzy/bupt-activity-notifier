"""One-time, per-channel authentication expiry notifications.

The local receipt file contains only an expiration timestamp and channel names.
No JWT, digest, account identifier or notification key is persisted here.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .api import ActivityClient, token_seconds_remaining
from .notifications import Notifier

WARNING_WINDOW_SECONDS = 24 * 60 * 60
BEIJING_TIME = timezone(timedelta(hours=8))


def _load_receipts(path: Path, expiry: int) -> dict[str, set[str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("expiry"), int)
        or not isinstance(data.get("receipts"), dict)
        or not all(
            key in ("expiring", "expired")
            and isinstance(value, list)
            and all(isinstance(channel, str) for channel in value)
            for key, value in data["receipts"].items()
        )
    ):
        raise ValueError("Invalid auth-notice receipts; refusing to reset deduplication.")
    if data["expiry"] != expiry:
        return {}
    return {kind: set(channels) for kind, channels in data["receipts"].items()}


def _save_receipts(path: Path, expiry: int, receipts: dict[str, set[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "expiry": expiry,
        "receipts": {name: sorted(channels) for name, channels in sorted(receipts.items())},
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def send_auth_notice_if_needed(
    client: ActivityClient,
    notifier: Notifier,
    state_path: Path,
    *,
    output: Callable[[str], None] = print,
) -> int:
    """Warn once per channel/expiry status. Never send while token is healthy."""
    remaining = token_seconds_remaining(client.credentials.token)
    if remaining is None or remaining > WARNING_WINDOW_SECONDS:
        return 0
    if not notifier.configured:
        return 0

    # The claim is decoded only for the expiration; the server validates identity.
    from .api import _jwt_claims

    expiry = int(_jwt_claims(client.credentials.token)["exp"])
    status = "expired" if remaining <= 0 else "expiring"
    local_expiry = datetime.fromtimestamp(expiry, tz=BEIJING_TIME).strftime("%Y-%m-%d %H:%M")
    title = "北邮第二课堂：登录已过期" if status == "expired" else "北邮第二课堂：请更新登录凭证"
    body = (
        f"第二课堂登录凭证到期时间（北京时间）：{local_expiry}。\n"
        "请在本机重新登录第二课堂，并更新项目私有 .env 中的 SECONDCLASS_TOKEN。\n"
        "监控不会自动登录、绕过验证或向任何人提供凭证。"
    )
    receipt_path = state_path.parent / "auth_notices.json"
    receipts = _load_receipts(receipt_path, expiry)
    sent = 0

    for channel in notifier.channels:
        if channel in receipts.get(status, set()):
            continue
        notifier.send_notice_channel(channel, title, body)
        receipts.setdefault(status, set()).add(channel)
        _save_receipts(receipt_path, expiry, receipts)
        sent += 1
        output(f"Authentication {status} notice sent via {channel}.")
    return sent
