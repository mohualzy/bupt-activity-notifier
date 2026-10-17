"""Validate and atomically sync an Edge-authorized second-classroom JWT.

This module is only called by the restricted native-messaging host. It never
reads browser profiles, passwords, cookies, or school login tickets. The
existing Windows watcher and its dedup state remain untouched.
"""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values

from .api import ActivityClient, APIError, AuthenticationExpired, Credentials, _jwt_claims, _jwt_subject

JWT_PATTERN = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\Z")
ENV_LINE = re.compile(rb"(?m)^(?:export[ \t]+)?SECONDCLASS_TOKEN[ \t]*=[^\r\n]*")
VALIDATOR = Callable[[str], None]
MIN_REMAINING = 3600
MIN_EXTENSION = 60


class ConfigurationError(Exception):
    """Never expose private file paths, credential contents, or exception strings."""


def token_claims(token: str) -> tuple[str, int, dict]:
    if not isinstance(token, str) or not 32 <= len(token) <= 8192 or not JWT_PATTERN.fullmatch(token):
        raise ValueError("Invalid JWT structure.")
    try:
        header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "==="))
        if header.get("alg") != "HS256":
            raise ValueError("Unexpected JWT signing algorithm.")
        claims = dict(_jwt_claims(token))
        subject = _jwt_subject(token)
        expiry = claims.get("exp")
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float, str)):
            raise ValueError("Missing expiration.")
        expiry = int(expiry)
        if expiry <= 0 or expiry >= 2**42:
            raise ValueError("Invalid expiration.")
        return subject, expiry, claims
    except (ValueError, TypeError, AttributeError, AuthenticationExpired, OverflowError) as exc:
        raise ValueError("Invalid JWT claims.") from None


def _source(root: Path) -> tuple[Path, str, str]:
    """Return source path, existing JWT, and source type (never print either)."""
    private = root / ".env"
    if not private.is_file() or private.is_symlink():
        raise ConfigurationError("Private configuration missing.")
    config = dotenv_values(private)
    if config.get("SECONDCLASS_TOKEN_FILE"):
        configured = Path(config["SECONDCLASS_TOKEN_FILE"]).expanduser()
        path = configured if configured.is_absolute() else root / configured
        path = path.resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or path.is_symlink():
            raise ConfigurationError("Invalid private token-file path.")
        token = path.read_text(encoding="utf-8").strip()
        return path, token, "token_file"
    token = (config.get("SECONDCLASS_TOKEN") or "").strip()
    if not token:
        raise ConfigurationError("Original token not configured.")
    return private, token, "dotenv"


def _safe_write(path: Path, data: bytes) -> None:
    """Atomic same-directory replacement with original file's mode preserved."""
    original_stat = path.stat()
    handle = None
    temporary = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb", prefix=".bupt-token-", suffix=".tmp", dir=str(path.parent),
            delete=False
        )
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.chmod(temporary, stat.S_IMODE(original_stat.st_mode))
        os.replace(temporary, path)
    finally:
        if handle is not None:
            handle.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _replace_current(source: Path, source_type: str, candidate: str, old: str) -> str:
    """Do not overwrite concurrent manual edits, even if the network check succeeded."""
    if source_type == "token_file":
        previous = source.read_text(encoding="utf-8").strip()
        if previous != old:
            return "raced_change"
        _safe_write(source, (candidate + "\n").encode("ascii"))
        return "updated"

    existing = source.read_bytes()
    records = list(ENV_LINE.finditer(existing))
    if len(records) != 1:
        return "bad_config"
    # Confirm that dotenv parsing and the raw line agree. Handles optional quoting.
    try:
        if (dotenv_values(source).get("SECONDCLASS_TOKEN") or "").strip() != old:
            return "raced_change"
    except Exception:
        return "bad_config"
    new_bytes = (b"SECONDCLASS_TOKEN=" + candidate.encode("ascii"))
    updated = existing[:records[0].start()] + new_bytes + existing[records[0].end():]
    _safe_write(source, updated)
    return "updated"


def check_student_api(jwt: str) -> None:
    """A signed and authorized JWT must actually list this student's activities."""
    ActivityClient(Credentials(jwt)).validate_connection()


def sync_candidate(
    token: str,
    root: Path,
    *,
    validator: VALIDATOR = check_student_api,
    now: float | None = None,
) -> str:
    """Return a fixed, credential-free result code; only verified JWTs are persisted."""
    now = time.time() if now is None else now
    try:
        new_sub, new_exp, new_claims = token_claims(token)
    except (ValueError, TypeError):
        return "invalid_candidate"
    if new_exp <= now + MIN_REMAINING:
        return "expired_candidate"

    try:
        source, old, source_type = _source(root)
    except (ConfigurationError, OSError, UnicodeError, ValueError):
        return "missing_current"
    try:
        old_sub, old_exp, old_claims = token_claims(old)
    except ValueError:
        return "bad_config"
    if new_sub != old_sub:
        return "wrong_account"
    # A management-context login must not silently replace a student-context JWT.
    for claim in ("login_type", "admin", "as_admin"):
        if old_claims.get(claim) != new_claims.get(claim):
            return "different_context"
    if token == old:
        return "already_current"
    if new_exp <= old_exp + MIN_EXTENSION:
        return "not_newer"

    try:
        validator(token)
    except (APIError, ValueError, OSError):
        return "verification_failed"
    except Exception:
        return "verification_failed"

    try:
        # A dedicated cross-process lock prevents concurrent tab overwrites.
        lockfile = root / ".state" / "edge_token_sync.lock"
        lockfile.parent.mkdir(parents=True, exist_ok=True)
        with lockfile.open("a+b") as stream:
            stream.seek(0)
            if stream.read(1) == b"":
                stream.seek(0)
                stream.write(b".")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return "busy"
            try:
                current_source, newest, current_type = _source(root)
                if current_source != source or current_type != source_type or newest != old:
                    return "raced_change"
                return _replace_current(source, source_type, token, old)
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except (ConfigurationError, OSError, UnicodeError, ValueError):
        return "bad_config"
