"""Read-only student activity API adapter.

Protocol confirmed on 2026-10-14 against an authorized browser session.
Tokens are supplied by the caller and are never persisted by this module.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
from pathlib import Path
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
        """Optionally reread a private token file on every polling cycle."""
        token_file = os.getenv("SECONDCLASS_TOKEN_FILE", "").strip()
        if token_file:
            try:
                token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                raise ValueError("Cannot read SECONDCLASS_TOKEN_FILE.") from None
        else:
            token = os.getenv("SECONDCLASS_TOKEN", "").strip()

        if not token or token == "replace_with_your_own_token":
            raise ValueError(
                "Missing SECONDCLASS_TOKEN or SECONDCLASS_TOKEN_FILE. "
                "Configure one privately (see .env.example)."
            )
        return cls(token=token)


def _jwt_claims(token: str) -> Mapping[str, Any]:
    """Decode untrusted claims. Only the server can verify the signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        result = json.loads(base64.urlsafe_b64decode(encoded))
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, IndexError, KeyError, TypeError, UnicodeDecodeError, binascii.Error):
        raise AuthenticationExpired("Invalid token format; authenticate again.") from None


def token_seconds_remaining(token: str, now: float | None = None) -> int | None:
    """Return seconds until the JWT exp (or None when missing)."""
    exp = _jwt_claims(token).get("exp")
    if exp is None:
        return None
    if isinstance(exp, bool):
        raise AuthenticationExpired("Invalid token expiration.")
    try:
        expiry = int(exp)
    except (TypeError, ValueError, OverflowError):
        raise AuthenticationExpired("Invalid token expiration.") from None
    return int(expiry - (time.time() if now is None else now))


def _jwt_subject(token: str) -> str:
    try:
        subject = str(_jwt_claims(token)["sub"])
        if not subject.isdecimal() or len(subject) > 30:
            raise ValueError
        return subject
    except (KeyError, ValueError):
        raise AuthenticationExpired("Invalid token subject; authenticate again.") from None


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
        remaining = token_seconds_remaining(self.credentials.token)
        if remaining is not None and remaining <= 0:
            raise AuthenticationExpired("Token expired; update your private token source.")
        try:
            response = self.session.get(
                self.base_url + path,
                params=params,
                headers={
                    "Authorization": "Bearer " + self.credentials.token,
                    "Accept": "application/json",
                    "User-Agent": "bupt-activity-notifier/0.4 (read-only)",
                },
                timeout=self.timeout,
                allow_redirects=False,
            )
            # The mini program's HTTP middleware honors x-real-status.
            # A successful-looking HTTP 200 may still carry a logical 401/403.
            status = response.status_code
            logical = response.headers.get("x-real-status", "")
            try:
                if logical:
                    status = int(logical)
            except (ValueError, TypeError):
                raise APIError("Invalid response status header.") from None
            if status in (401, 403):
                raise AuthenticationExpired("Access denied or login expired (401/403).")
            if status >= 400 or 300 <= response.status_code < 400:
                raise APIError("Second Classroom GET returned an unsuccessful status.")
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
