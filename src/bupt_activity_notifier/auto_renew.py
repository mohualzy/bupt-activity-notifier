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
    """Sanitized sign-in failure; never print browser or credential details."""


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
        raise RenewalError("Automatic login has not been configured.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RenewalError("Playwright is not installed.") from None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=headless)
            try:
                context = browser.new_context(locale="zh-CN")
                page = context.new_page()
                page.goto("https://dekt.bupt.edu.cn/login", wait_until="domcontentloaded", timeout=20_000)
                page.locator("#username").fill(username, timeout=10_000)
                page.locator("#password").fill(password, timeout=10_000)
                page.locator("button:has-text('登录')").first.click(timeout=10_000)
                deadline = time.monotonic() + (100 if not headless else 28)
                while time.monotonic() < deadline:
                    token = page.evaluate("window.localStorage.getItem('secondclass.tokenv3') || ''")
                    if token:
                        return token
                    page.wait_for_timeout(1000)
                raise RenewalError(
                    "Official sign-in did not complete; manual CAPTCHA or login may be required."
                )
            finally:
                browser.close()
    except RenewalError:
        raise
    except Exception:
        # Errors from Playwright may contain current URLs, form details, and
        # browser debugging strings. Never propagate or log them.
        raise RenewalError("Browser sign-in failed; complete any challenge manually.") from None


def verify_candidate(candidate: str, previous: str) -> None:
    """Reject account switches and tokens that cannot read the student's API."""
    try:
        if _jwt_subject(candidate) != _jwt_subject(previous):
            raise RenewalError("New session has a different student account.")
        new_left = token_seconds_remaining(candidate)
        old_left = token_seconds_remaining(previous)
        if (
            new_left is None or new_left < MIN_NEW_LIFETIME_SECONDS
            or (old_left is not None and new_left <= old_left + 3600)
        ):
            raise RenewalError("New JWT did not extend the session.")
        # Validate the exact student endpoints, not the management login UI.
        ActivityClient(Credentials(candidate)).validate_connection()
    except RenewalError:
        raise
    except (APIError, ValueError):
        raise RenewalError("New JWT cannot query the same student activity API.") from None


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
            raise RenewalError("Cannot save the retry guard; sign-in was not attempted.") from None

    try:
        pair = read_login()
        if not pair:
            raise RenewalError("Windows Credential Manager has no configured login.")
        token = browser_sign_in(*pair, headless=headless)
        verify_candidate(token, previous)
        save_renewed_token(token)
        _clear_retry(state_path)
        return True
    except RenewalError:
        if force:
            # A manual trial must not schedule unexpected background retries.
            return _failed_manual()
        raise
    except (SecretStoreError, OSError):
        raise RenewalError("Credential storage failed; existing token was not changed.") from None


def _failed_manual() -> bool:
    # Preserve exception as a RenewalError without exposing its message to logs.
    raise RenewalError("Manual sign-in trial did not pass verification.") from None
