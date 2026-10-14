"""Command-line entry point. No persistent task is created automatically."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .api import ActivityClient, Credentials
from .filtering import Activity, matches_shahe_checkin_no_checkout, render_activity
from .monitor import run_once
from .notifications import Notifier

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
    {
        "id": 1002,
        "name": "示例：沙河需签退活动（虚构）",
        "area": 1,
        "location": "图书馆",
        "demands": 6,
    },
    {
        "id": 1003,
        "name": "示例：未知签到规则（虚构）",
        "area": 1,
        "location": "公教楼",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bupt-activity",
        description="Unofficial read-only BUPT second-classroom activity monitor.",
    )
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--demo", action="store_true", help="Filter synthetic samples offline.")
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
    try:
        credentials = Credentials.from_environment()
        client = ActivityClient(credentials, base_url=os.getenv("SECONDCLASS_BASE_URL", "https://dekt.bupt.edu.cn"))
        notifier = Notifier.from_environment()
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))

    if args.once:
        run_once(client, notifier, args.state, dry_run=args.dry_run)
        return 0

    interval = max(60, int(os.getenv("POLL_SECONDS", "300")))
    print(f"Watching read-only activity list every {interval}s; Ctrl+C to stop.")
    try:
        while True:
            try:
                run_once(client, notifier, args.state, dry_run=args.dry_run)
            except Exception as exc:
                # Never include tokens, request URLs, or raw server responses.
                print(f"Poll failed ({type(exc).__name__}); retrying next interval.")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopped.")
        return 0
