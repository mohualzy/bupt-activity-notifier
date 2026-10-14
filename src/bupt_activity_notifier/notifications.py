"""Optional notification providers with credential-safe exception handling.

External endpoints are write-only *notifications*, not school account actions.
Each provider has its own receipt in monitor.py to prevent cross-provider repeats.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

import requests

from .filtering import Activity, render_activity


class NotificationError(RuntimeError):
    """Provider failure, with no secrets, URLs, or request contents."""


@dataclass
class Notifier:
    serverchan_key: str = ""
    onebot_url: str = ""
    onebot_token: str = ""
    onebot_user_id: str = ""
    onebot_group_id: str = ""
    session: requests.Session | None = None

    @classmethod
    def from_environment(cls) -> "Notifier":
        return cls(
            serverchan_key=os.getenv("SERVERCHAN_SENDKEY", "").strip(),
            onebot_url=os.getenv("ONEBOT_URL", "").strip(),
            onebot_token=os.getenv("ONEBOT_ACCESS_TOKEN", "").strip(),
            onebot_user_id=os.getenv("ONEBOT_USER_ID", "").strip(),
            onebot_group_id=os.getenv("ONEBOT_GROUP_ID", "").strip(),
        )

    @property
    def channels(self) -> tuple[str, ...]:
        channels = []
        if self.serverchan_key:
            channels.append("serverchan")
        if self.onebot_url and self.onebot_user_id:
            channels.append("onebot_private")
        if self.onebot_url and self.onebot_group_id:
            channels.append("onebot_group")
        return tuple(channels)

    @property
    def configured(self) -> bool:
        return bool(self.channels)

    def _serverchan(self, body: str, client: requests.Session) -> None:
        response = client.post(
            "https://sctapi.ftqq.com/" + quote(self.serverchan_key, safe="") + ".send",
            data={"title": "北邮第二课堂：符合条件的新活动", "desp": body},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("code") not in (0, "0"):
            raise NotificationError("ServerChan refused the notification.")

    def _onebot(self, channel: str, body: str, client: requests.Session) -> None:
        from urllib.parse import urlsplit

        url = urlsplit(self.onebot_url)
        if url.username or url.password or url.query or url.fragment:
            raise NotificationError("OneBot endpoint contains unsupported URL components.")
        local = url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost")
        remote = url.scheme == "https" and bool(url.hostname)
        if not (local or remote):
            raise NotificationError("OneBot endpoint requires HTTPS, or localhost HTTP.")

        if channel == "onebot_private":
            path = "/send_private_msg"
            target = {"user_id": int(self.onebot_user_id)}
        elif channel == "onebot_group":
            path = "/send_group_msg"
            target = {"group_id": int(self.onebot_group_id)}
        else:
            raise NotificationError("Unknown OneBot channel.")

        headers = {"Authorization": "Bearer " + self.onebot_token} if self.onebot_token else {}
        response = client.post(
            self.onebot_url.rstrip("/") + path,
            headers=headers,
            json={**target, "message": body, "auto_escape": True},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("status") != "ok" or result.get("retcode") != 0:
            raise NotificationError("OneBot refused the notification.")

    def send_channel(self, channel: str, activity: Activity) -> None:
        """Send a single activity to one channel. On any failure, never expose secrets."""
        if channel not in self.channels:
            raise NotificationError("Requested notification channel is not configured.")
        client = self.session or requests.Session()
        body = render_activity(activity)
        try:
            if channel == "serverchan":
                self._serverchan(body, client)
            else:
                self._onebot(channel, body, client)
        except NotificationError:
            raise
        except (requests.RequestException, ValueError, TypeError, KeyError):
            raise NotificationError(f"Notification delivery failed ({channel}).") from None

    def send(self, activity: Activity) -> None:
        """Compatibility helper; monitor uses send_channel for per-channel receipts."""
        for channel in self.channels:
            self.send_channel(channel, activity)
