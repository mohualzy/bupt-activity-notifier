"""Unofficial, read-only API adapter. End-to-end access is not yet verified."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

import requests

BASE_URL = "https://dekt.bupt.edu.cn"


class APIError(RuntimeError):
    """The service returned a response that this client cannot use."""


@dataclass(frozen=True)
class Credentials:
    token: str
    college_id: str
    class_id: str
    grade: str
    role_id: str
    digest: str
    is_group: int = 0

    @classmethod
    def from_environment(cls) -> "Credentials":
        env = {
            "token": "SECONDCLASS_TOKEN",
            "college_id": "SECONDCLASS_COLLEGE_ID",
            "class_id": "SECONDCLASS_CLASS_ID",
            "grade": "SECONDCLASS_GRADE",
            "role_id": "SECONDCLASS_ROLE_ID",
            "digest": "SECONDCLASS_DIGEST",
        }
        missing = [key for key in env.values() if not os.getenv(key)]
        if missing:
            raise ValueError(
                "Missing environment variables: " + ", ".join(missing)
                + ". See .env.example; never commit credentials."
            )
        return cls(
            **{name: os.environ[key] for name, key in env.items()},
            is_group=int(os.getenv("SECONDCLASS_IS_GROUP", "0")),
        )


def unwrap_activity_list(payload: Any) -> list[Mapping[str, Any]]:
    """Accept known and nested envelope variants without inventing records."""
    if not isinstance(payload, dict):
        raise APIError("Unexpected API response: JSON root must be an object.")
    if payload.get("error") not in (None, False, "", 0):
        raise APIError("The API reported an error; response data not used.")
    value = payload.get("data")
    if isinstance(value, dict):
        value = value.get("data")
    if not isinstance(value, list):
        raise APIError("Unexpected API response: data must be an activity array.")
    if not all(isinstance(item, dict) for item in value):
        raise APIError("Unexpected API response: activity entries must be objects.")
    return value


class ActivityClient:
    """Only issues GET requests; never signs up, signs in, or changes subscriptions."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        base_url: str = BASE_URL,
        session: requests.Session | None = None,
        timeout: int = 15,
    ):
        if not base_url.startswith("https://"):
            raise ValueError("Only HTTPS API endpoints are allowed.")
        if base_url.rstrip("/") != BASE_URL:
            raise ValueError("Only the official second-classroom API host is allowed.")
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def list_activities(self) -> list[Mapping[str, Any]]:
        c = self.credentials
        response = self.session.get(
            self.base_url + "/api/v1/activity",
            params={
                "college_id": c.college_id,
                "class_id": c.class_id,
                "grade": c.grade,
                "role_id": c.role_id,
                "digest": c.digest,
                "is_group": c.is_group,
            },
            headers={
                "Authorization": "Bearer " + c.token,
                "Accept": "application/json",
                "User-Agent": "bupt-activity-notifier/0.1 (read-only)",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            return unwrap_activity_list(response.json())
        except (ValueError, TypeError) as exc:
            raise APIError("The service returned invalid JSON or an invalid payload.") from exc
