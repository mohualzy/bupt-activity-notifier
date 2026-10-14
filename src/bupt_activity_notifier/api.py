"""Read-only student activity API adapter.

Protocol confirmed on 2026-10-14 against an authorized browser session.
Tokens are supplied by the caller and are never persisted by this module.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

import requests

BASE_URL = "https://dekt.bupt.edu.cn"


class APIError(RuntimeError):
    """A sanitized error, without request URLs, tokens or user data."""


class AuthenticationExpired(APIError):
    """The supplied token is invalid, absent, or expired."""


@dataclass(frozen=True)
class Credentials:
    token: str

    @classmethod
    def from_environment(cls) -> "Credentials":
        token = os.getenv("SECONDCLASS_TOKEN", "").strip()
        if not token or token == "replace_with_your_own_token":
            raise ValueError(
                "Missing SECONDCLASS_TOKEN. Set it privately in .env "
                "(see .env.example). Never commit credentials."
            )
        return cls(token=token)


def _jwt_subject(token: str) -> str:
    """Decode the JWT subject for the *official* current-user path.

    Decoding a JWT is not signature verification; the server authenticates it.
    """
    try:
        encoded = token.split(".")[1]
        encoded += "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded))
        subject = str(payload["sub"])
        if not subject.isdecimal() or len(subject) > 30:
            raise ValueError
        return subject
    except (ValueError, IndexError, KeyError, TypeError, UnicodeDecodeError, binascii.Error):
        raise AuthenticationExpired("Invalid token format; authenticate again.") from None


def _unwrap_payload(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, dict):
        raise APIError("Unexpected API response: JSON root is not an object.")
    if payload.get("error") not in (None, False, "", 0):
        raise APIError("Second Classroom API reported an error.")
    if payload.get("status") not in ("ok", 0, None, True):
        raise APIError("Second Classroom API did not report success.")
    return payload


def unwrap_activity_list(payload: Any) -> list[Mapping[str, Any]]:
    """Validate the API's live {status, data, digest, error} response."""
    response = _unwrap_payload(payload)
    data = response.get("data")
    if not isinstance(data, list):
        raise APIError("Unexpected API response: data is not an activity array.")
    if not all(isinstance(item, dict) for item in data):
        raise APIError("Unexpected API response: an activity is not an object.")
    return data


class ActivityClient:
    """Only uses GET requests; no sign-up or attendance operations."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        base_url: str = BASE_URL,
        session: requests.Session | None = None,
        timeout: int = 15,
    ):
        if base_url.rstrip("/") != BASE_URL:
            raise ValueError("The official HTTPS host is the only allowed API base.")
        self.credentials = credentials
        self.base_url = BASE_URL
        self.session = session or requests.Session()
        self.timeout = timeout

    def _get(self, path: str, *, params: dict[str, str | int] | None = None) -> Mapping[str, Any]:
        try:
            response = self.session.get(
                self.base_url + path,
                params=params,
                headers={
                    "Authorization": "Bearer " + self.credentials.token,
                    "Accept": "application/json",
                    "User-Agent": "bupt-activity-notifier/0.2 (read-only)",
                },
                timeout=self.timeout,
            )
            if response.status_code in (401, 403):
                raise AuthenticationExpired("Access denied or login expired (401/403).")
            response.raise_for_status()
            return _unwrap_payload(response.json())
        except AuthenticationExpired:
            raise
        except requests.RequestException:
            # requests HTTPError may contain URL query parameters (including digest).
            raise APIError("Second Classroom GET request failed.") from None
        except (ValueError, TypeError):
            raise APIError("Second Classroom returned invalid JSON.") from None

    def get_current_user_context(self) -> tuple[Mapping[str, Any], str]:
        """Get the authenticated student's activity-query fields and digest."""
        subject = _jwt_subject(self.credentials.token)
        payload = self._get("/api/v1/user/" + quote(subject, safe=""))
        user = payload.get("data")
        digest = payload.get("digest")
        if not isinstance(user, dict) or digest is None or str(digest) == "":
            raise APIError("User response does not contain student data and digest.")
        required = ("college_id", "class_id", "grade", "role_id")
        if any(key not in user or user[key] is None for key in required):
            raise APIError("User response lacks required activity query fields.")
        return user, str(digest)

    def list_activities(self, *, is_group: int = 0) -> list[Mapping[str, Any]]:
        user, digest = self.get_current_user_context()
        params = {key: str(user[key]) for key in ("college_id", "class_id", "grade", "role_id")}
        params["digest"] = digest
        params["is_group"] = int(is_group)
        response = self._get("/api/v1/activity", params=params)
        return unwrap_activity_list(response)

    def validate_connection(self) -> dict[str, Any]:
        """Return non-sensitive diagnostics, not student identifiers or activities."""
        items = self.list_activities()
        keys = sorted({key for item in items for key in item})
        return {"http": 200, "activity_count": len(items), "activity_fields": keys}
