"""CLI: offline demo, privacy-preserving diagnostics, and polling."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .api import (
    APIError,
    ActivityClient,
    AuthenticationExpired,
    Credentials,
    token_seconds_remaining,
)
from .auth_notice import send_auth_notice_if_needed
from .filtering import Activity, matches_shahe_checkin_no_checkout, render_activity
from .monitor import run_once
from .notifications import NotificationError, Notifier

EXAMPLES = [
    {
        "id": 1001,
        "name": "示例：沙河签到免签退活动（虚构）",
        "area": 1,
        "location": "教学楼",
        "demands": 2,
        "activity_start_time": "2026-12-01T18:00:00",
        "activity_end_time": "2026-12-01T19:00:00",
    },
    {"id": 1002, "name": "示例：沙河需签退活动（虚构）", "area": 1, "demands": 6},
    {"id": 1003, "name": "示例：未知签到规则（虚构）", "area": 1},
]


def make_client() -> ActivityClient:
    """Read the token source each call. A private file can be rotated without restart."""
    credentials = Credentials.from_environment()
    return ActivityClient(
        credentials,
        base_url=os.getenv("SECONDCLASS_BASE_URL", "https://dekt.bupt.edu.cn"),
    )


def _token_warning(client: ActivityClient) -> str | None:
    remaining = token_seconds_remaining(client.credentials.token)
    if remaining is not None and 0 < remaining <= 24 * 3600:
        return "Token expires within 24h. Update the private token source before expiration."
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bupt-activity",
        description="Unofficial read-only BUPT second-classroom activity monitor.",
    )
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--demo", action="store_true", help="Filter synthetic samples offline.")
    options.add_argument("--doctor", action="store_true", help="Validate live API without printing identities.")
    options.add_argument("--test-push", action="store_true", help="Send one synthetic push to configured channels.")
    options.add_argument("--once", action="store_true", help="Poll the activity API once.")
    options.add_argument("--watch", action="store_true", help="Poll repeatedly (Ctrl+C to stop).")
    parser.add_argument("--dry-run", action="store_true", help="Print matches; do not send or save.")
    parser.add_argument("--state", type=Path, default=Path(".state/seen.json"))
    args = parser.parse_args(argv)

    if args.demo:
        print("Synthetic example only; no network requests:")
        for item in EXAMPLES:
            activity = Activity.from_raw(item)
            if matches_shahe_checkin_no_checkout(activity):
                print(render_activity(activity))
        return 0

    load_dotenv()
    notifier = Notifier.from_environment()

    if args.test_push:
        if not notifier.configured:
            print("No notification channel configured; see .env.example.")
            return 2
        sample = Activity(
            id="synthetic-test", title="【测试】第二课堂通知连接", area=1,
            demands=2, location="模拟活动（不是实际报名）",
            start="", end="",
        )
        try:
            notifier.send(sample)
            print("Test notification accepted by configured provider(s).")
            return 0
        except NotificationError:
            print("Test notification failed; check channel configuration privately.")
            return 1

    if args.doctor:
        try:
            client = make_client()
            outcome = client.validate_connection()
            print("Authenticated read-only API connection succeeded (HTTP 200).")
            print(f"Activities returned: {outcome['activity_count']}.")
            print("Activity keys: " + ", ".join(outcome["activity_fields"]))
            if warning := _token_warning(client):
                print(warning)
            return 0
        except (APIError, ValueError) as exc:
            print(f"Connection validation failed ({type(exc).__name__}).")
            return 1

    if args.once:
        try:
            client = make_client()
            result = run_once(client, notifier, args.state, dry_run=args.dry_run)
            if warning := _token_warning(client):
                print(warning)
            return 0
        except (APIError, NotificationError, OSError, ValueError) as exc:
            # Never print exception text that could contain a URL with digest.
            print(f"Poll failed ({type(exc).__name__}).")
            return 1

    interval = max(60, int(os.getenv("POLL_SECONDS", "300")))
    print(f"Watching read-only activities every {interval}s; Ctrl+C to stop.")
    previous_status = ""
    try:
        while True:
            try:
                # Read private .env again so replacing SECONDCLASS_TOKEN or
                # ServerChan SendKey works without restarting the watcher.
                load_dotenv(override=True)
                notifier = Notifier.from_environment()
                client = make_client()
                if warning := _token_warning(client):
                    if previous_status != "expiring":
                        print(warning)
                    previous_status = "expiring"
                if not args.dry_run:
                    try:
                        send_auth_notice_if_needed(client, notifier, args.state)
                    except (NotificationError, OSError, ValueError) as exc:
                        # A failed optional reminder must not interrupt activity checks.
                        print(f"Auth reminder failed ({type(exc).__name__}); retrying later.")
                run_once(client, notifier, args.state, dry_run=args.dry_run)
                if previous_status != "expiring":
                    previous_status = ""
            except AuthenticationExpired:
                if previous_status != "expired":
                    print("Authentication expired. Update your private Token source; watcher will retry.")
                previous_status = "expired"
            except (APIError, NotificationError, OSError, ValueError) as exc:
                if previous_status != type(exc).__name__:
                    print(f"Polling paused by {type(exc).__name__}; will retry.")
                previous_status = type(exc).__name__
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
