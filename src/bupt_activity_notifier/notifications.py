"""Optional opt-in delivery adapters; never put keys in committed files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

import requests

from .filtering import Activity, render_activity


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
            serverchan_key=os.getenv("SERVERCHAN_SENDKEY", ""),
            onebot_url=os.getenv("ONEBOT_URL", ""),
            onebot_token=os.getenv("ONEBOT_ACCESS_TOKEN", ""),
            onebot_user_id=os.getenv("ONEBOT_USER_ID", ""),
            onebot_group_id=os.getenv("ONEBOT_GROUP_ID", ""),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.serverchan_key
            or (self.onebot_url and (self.onebot_user_id or self.onebot_group_id))
        )

    def send(self, activity: Activity) -> None:
        client = self.session or requests.Session()
        body = render_activity(activity)
        if self.serverchan_key:
            response = client.post(
                "https://sctapi.ftqq.com/" + quote(self.serverchan_key, safe="") + ".send",
                data={"title": "北邮第二课堂：符合筛选条件的活动", "desp": body},
                timeout=15,
            )
            response.raise_for_status()
            # ServerChan uses a JSON-level code even on HTTP 200.
            result = response.json()
            if result.get("code") not in (0, "0"):
                raise RuntimeError("ServerChan rejected the notification.")
        if self.onebot_url and (self.onebot_user_id or self.onebot_group_id):
            if not self.onebot_url.startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
                raise ValueError("OneBot must use localhost HTTP or HTTPS.")
            endpoint = self.onebot_url.rstrip("/")
            headers = {"Authorization": "Bearer " + self.onebot_token} if self.onebot_token else {}
            targets = []
            if self.onebot_user_id:
                targets.append(("/send_private_msg", {"user_id": int(self.onebot_user_id)}))
            if self.onebot_group_id:
                targets.append(("/send_group_msg", {"group_id": int(self.onebot_group_id)}))
            for route, target in targets:
                response = client.post(
                    endpoint + route,
                    headers=headers,
                    json={**target, "message": body},
                    timeout=15,
                )
                response.raise_for_status()
                result = response.json()
                if result.get("status") == "failed" or result.get("retcode", 0) != 0:
                    raise RuntimeError("OneBot rejected the notification.")
