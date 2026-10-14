"""Conservative, opt-in browser reauthentication for the student activity watcher.

Adapted conceptually from MaplumeX/bupt_notification/web_login.py.
No stealth flags, CAPTCHA bypass, Edge profile scraping, or SSO ticket reuse.
The only persistent secrets are stored in Windows Credential Manager.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

from .api import (
    APIError, ActivityClient, AuthenticationExpired, Credentials, _jwt_subject,
    token_seconds_remaining,
)
from .win_credentials import (
    SecretStoreError, read_login, read_renewed_token, save_renewed_token,
)

TOKEN_KEY = "secondclass.tokenv3"
RENEW_WINDOW_SECONDS = 24 * 3600
MIN_NEW_LIFETIME_SECONDS = 24 * 3600
RETRY_DELAY_SECONDS = 12 * 3600
RETRY_STATE_FILENAME = "auto_renew_retry.json"


class RenewalError(RuntimeError):
    """Sanitized sign-in failure with a fixed, non-secret diagnostic code."""

    CODES = frozenset({
        "missing_login", "playwright_unavailable", "browser_error",
        "verification_required", "login_rejected", "login_not_completed",
        "wrong_student", "not_renewed", "student_api_rejected",
        "credential_store", "retry_guard",
    })

    def __init__(self, message: str, *, code: str = "browser_error"):
        super().__init__(message)
        self.code = code if code in self.CODES else "browser_error"


def enabled() -> bool:
    return os.getenv("SECONDCLASS_AUTO_RENEW", "").strip().lower() in ("1", "yes", "true", "on")


def choose_token(original: str) -> str:
    """Use only a newer, same-account token from protected Windows credentials."""
    if not enabled():
        return original
    try:
        cached = read_renewed_token()
        if not cached:
            return original
        if _jwt_subject(cached) != _jwt_subject(original):
            return original
        newer = token_seconds_remaining(cached)
        old = token_seconds_remaining(original)
        if newer is not None and newer > 0 and (old is None or newer > old):
            return cached
    except (AuthenticationExpired, SecretStoreError, ValueError):
        pass
    return original


def _retry_allowed(state_path: Path, now: float) -> bool:
    path = state_path.parent / RETRY_STATE_FILENAME
    if not path.exists():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("retry_after"), (int, float))
            or isinstance(data.get("retry_after"), bool)
        ):
            return False  # Corrupted state must not cause a login storm.
        return now >= float(data["retry_after"])
    except (ValueError, OSError, UnicodeError):
        return False


def _set_retry(state_path: Path, now: float) -> None:
    path = state_path.parent / RETRY_STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"version": 1, "retry_after": int(now + RETRY_DELAY_SECONDS)}),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _clear_retry(state_path: Path) -> None:
    (state_path.parent / RETRY_STATE_FILENAME).unlink(missing_ok=True)


def browser_sign_in(username: str, password: str, *, headless: bool = True) -> str:
    """Let the official web login create a session; do not defeat challenges."""
    if not username or not password:
        raise RenewalError("Automatic login has not been configured.", code="missing_login")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RenewalError("Playwright is not installed.", code="playwright_unavailable") from None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=headless)
            try:
                context = browser.new_context(locale="zh-CN")
                page = context.new_page()
                statuses: list[int] = []

                def note_login_status(response: object) -> None:
                    # Only retain an HTTP status integer for the official
                    # login endpoint. Never access requests or response bodies.
                    try:
                        url = urlsplit(response.url)
                        if (
                            url.hostname != "dekt.bupt.edu.cn"
                            or url.path != "/api/v1/auth/sessions"
                            or response.request.method != "POST"
                        ):
                            return
                        raw = response.headers.get("x-real-status", "")
                        status = int(raw) if raw.isdecimal() else int(response.status)
                        statuses.append(status)
                    except Exception:
                        # An inaccessible network event must never crash the
                        # login flow or expose its request information.
                        return

                page.on("response", note_login_status)
                page.goto("https://dekt.bupt.edu.cn/login", wait_until="domcontentloaded", timeout=20_000)
                page.locator("#username").fill(username, timeout=10_000)
                page.locator("#password").fill(password, timeout=10_000)
                page.locator("button:has-text('登录')").first.click(timeout=10_000)
                deadline = time.monotonic() + (100 if not headless else 28)
                while time.monotonic() < deadline:
                    # A redirect can briefly destroy the JS execution context
                    # exactly while the login succeeds. Such transient
                    # navigation errors should not abort verification.
                    try:
                        token = page.evaluate(
                            "window.localStorage.getItem('secondclass.tokenv3') || ''"
                        )
                        if token:
                            return token
                    except Exception:
                        pass
                    try:
                        page.wait_for_timeout(1000)
                    except Exception:
                        break
                if any(code in (419, 420) for code in statuses):
                    raise RenewalError(
                        "The official website requires an interactive verification.",
                        code="verification_required",
                    )
                if any(code in (401, 403) for code in statuses):
                    raise RenewalError("The official sign-in was rejected.", code="login_rejected")
                raise RenewalError(
                    "The official sign-in did not issue a JWT within the time window.",
                    code="login_not_completed",
                )
            finally:
                browser.close()
    except RenewalError:
        raise
    except Exception:
        # Errors from Playwright may contain current URLs, form details, and
        # browser debugging strings. Never propagate or log them.
        raise RenewalError(
            "Browser sign-in failed; complete any challenge manually.",
            code="browser_error",
        ) from None


def verify_candidate(candidate: str, previous: str) -> None:
    """Reject account switches and tokens that cannot read the student's API."""
    try:
        if _jwt_subject(candidate) != _jwt_subject(previous):
            raise RenewalError("New session has a different student account.", code="wrong_student")
        new_left = token_seconds_remaining(candidate)
        old_left = token_seconds_remaining(previous)
        if (
            new_left is None or new_left < MIN_NEW_LIFETIME_SECONDS
            or (old_left is not None and new_left <= old_left + 3600)
        ):
            raise RenewalError("New JWT did not extend the session.", code="not_renewed")
        # Validate the exact student endpoints, not the management login UI.
        ActivityClient(Credentials(candidate)).validate_connection()
    except RenewalError:
        raise
    except (APIError, ValueError):
        raise RenewalError(
            "New JWT cannot query the same student activity API.",
            code="student_api_rejected",
        ) from None


def renew_if_due(client: ActivityClient, state_path: Path, *, force: bool = False, headless: bool = True) -> bool:
    """Return True only after a validated new token is safely persisted."""
    if not force and not enabled():
        return False
    previous = client.credentials.token
    remaining = token_seconds_remaining(previous)
    if not force and (remaining is None or remaining > RENEW_WINDOW_SECONDS):
        return False
    now = time.time()
    if not force and not _retry_allowed(state_path, now):
        return False

    if not force:
        # Write retry first so crashes also cannot cause repeated sign-in.
        try:
            _set_retry(state_path, now)
        except OSError:
            raise RenewalError(
                "Cannot save the retry guard; sign-in was not attempted.",
                code="retry_guard",
            ) from None

    try:
        pair = read_login()
        if not pair:
            raise RenewalError(
                "Windows Credential Manager has no configured login.", code="missing_login"
            )
        token = browser_sign_in(*pair, headless=headless)
        verify_candidate(token, previous)
        save_renewed_token(token)
        _clear_retry(state_path)
        return True
    except RenewalError:
        # Raise only our fixed-message errors. CLI prints a whitelisted code,
        # never arbitrary browser exceptions, identity, or Token information.
        raise
    except (SecretStoreError, OSError):
        raise RenewalError(
            "Credential storage failed; existing token was not changed.",
            code="credential_store",
        ) from None
