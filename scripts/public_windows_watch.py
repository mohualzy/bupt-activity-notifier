"""Windows background runner for supplementary zero-login BUPT notice leads.

Completely independent of the primary Second Classroom watcher. Reads only
the already configured ServerChan/OneBot delivery credentials, NEVER the JWT.
"""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import msvcrt
import os
from pathlib import Path
import sys
import time

from dotenv import dotenv_values

PUBLIC_ROOT = Path(__file__).resolve().parent.parent
STABLE_ROOT = PUBLIC_ROOT.parent / "bupt-activity-notifier"
STATE_DIR = STABLE_ROOT / ".state"
LOG_DIR = STABLE_ROOT / "logs"
INTERVAL_SECONDS = 30 * 60


def get_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bupt-public-leads")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handle = RotatingFileHandler(
            LOG_DIR / "public_watch.log",
            encoding="utf-8", maxBytes=800_000, backupCount=2,
        )
        handle.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handle)
    return logger


def load_notification_channels():
    # dotenv_values does not copy env-file contents into process environment.
    # Never inspect or export the Second Classroom JWT.
    from bupt_activity_notifier.notifications import Notifier

    private = STABLE_ROOT / ".env"
    if not private.is_file():
        return Notifier()
    config = dotenv_values(private)
    return Notifier(
        serverchan_key=str(config.get("SERVERCHAN_SENDKEY") or "").strip(),
        onebot_url=str(config.get("ONEBOT_URL") or "").strip(),
        onebot_token=str(config.get("ONEBOT_ACCESS_TOKEN") or "").strip(),
        onebot_user_id=str(config.get("ONEBOT_USER_ID") or "").strip(),
        onebot_group_id=str(config.get("ONEBOT_GROUP_ID") or "").strip(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Anonymous BUPT campus event leads.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not (STABLE_ROOT / "logs").exists():
        print("Stable project not found. Public observer was not started.")
        return 2

    sys.path.insert(0, str(PUBLIC_ROOT / "src"))
    from bupt_activity_notifier.public_monitor import run_public_poll

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logger = get_logger()
    if args.once or args.dry_run:
        notifier = load_notification_channels()
        report = run_public_poll(
            notifier, STATE_DIR / "public_seen.json",
            dry_run=args.dry_run,
            output=lambda line: logger.info(line),
        )
        print(
            f"Sources healthy: {report.sources_ok}; public entries: {report.discovered}; "
            f"relevant new leads: {report.leads}; notifications: {report.delivered}."
        )
        return 0 if report.sources_ok else 1

    # Separate lock, state, log and Windows task from the existing official
    # student watcher; never lock or modify its state/seen.json.
    lock_path = STATE_DIR / "public_watch.lock"
    lock = lock_path.open("a+b")
    if lock.tell() == 0:
        lock.write(b"\0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        logger.info("Public activity observer already running; exiting.")
        lock.close()
        return 0

    try:
        logger.info("Public source observer started (pid=%s).", os.getpid())
        while True:
            try:
                notifier = load_notification_channels()
                run_public_poll(
                    notifier, STATE_DIR / "public_seen.json",
                    output=lambda line: logger.info(line),
                )
            except Exception as exc:
                # Never send or log URL/token-bearing raw exception messages.
                logger.error("Public observation failed (%s).", type(exc).__name__)
            time.sleep(INTERVAL_SECONDS)
    finally:
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
