"""Polling and per-activity deduplication, with a safe first-run baseline."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .filtering import Activity, matches_shahe_checkin_no_checkout, render_activity
from .notifications import Notifier


@dataclass(frozen=True)
class Result:
    total: int
    matched: int
    notified: int
    initialized: bool = False


def read_seen(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("seen_ids"), list):
        raise ValueError("Invalid seen-state file; refusing to reset deduplication.")
    return {str(value) for value in data["seen_ids"]}


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps({"seen_ids": sorted(seen)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def run_once(
    client: object,
    notifier: Notifier,
    state_path: Path,
    *,
    output: Callable[[str], None] = print,
    dry_run: bool = False,
) -> Result:
    raw = client.list_activities()
    activities: list[Activity] = []
    for record in raw:
        try:
            activities.append(Activity.from_raw(record))
        except ValueError:
            output("Skipped an activity missing its id.")
    matched = [a for a in activities if matches_shahe_checkin_no_checkout(a)]

    if dry_run:
        output(f"[dry-run] {len(raw)} fetched, {len(matched)} matched; state unchanged.")
        for activity in matched:
            output(render_activity(activity))
        return Result(len(raw), len(matched), 0)

    if not state_path.exists():
        # Remember only matches: a changed activity becoming eligible is still new.
        save_seen(state_path, {a.id for a in matched})
        output(f"First-run baseline saved ({len(matched)} matches). No notifications sent.")
        return Result(len(raw), len(matched), 0, initialized=True)

    seen = read_seen(state_path)
    new_matches = [a for a in matched if a.id not in seen]
    sent = 0
    for activity in new_matches:
        if not notifier.configured:
            output("[preview, no channel configured]\n" + render_activity(activity))
            continue
        notifier.send(activity)  # Do not mark an activity seen after delivery failure.
        seen.add(activity.id)
        save_seen(state_path, seen)  # Commit per successful notification.
        sent += 1
        output(f"Notified activity {activity.id}.")

    output(f"Fetched={len(raw)}, matched={len(matched)}, new_matches={len(new_matches)}, sent={sent}.")
    return Result(len(raw), len(matched), sent)
