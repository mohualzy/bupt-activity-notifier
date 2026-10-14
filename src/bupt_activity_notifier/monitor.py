"""Read-only polling with crash-resistant per-channel delivery receipts.

Newly matched activities are considered complete only once every configured
notification channel confirms delivery. State never stores credentials.
"""

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
    deliveries: int = 0


@dataclass
class SeenState:
    seen_ids: set[str]
    delivered: dict[str, set[str]]


def read_state(path: Path) -> SeenState:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("seen_ids"), list):
        raise ValueError("Invalid seen-state file; refusing to reset deduplication.")
    raw_delivered = data.get("delivered", {})
    if not isinstance(raw_delivered, dict) or not all(
        isinstance(name, str) and isinstance(ids, list)
        for name, ids in raw_delivered.items()
    ):
        raise ValueError("Invalid delivery ledger; refusing to reset deduplication.")
    return SeenState(
        seen_ids={str(item) for item in data["seen_ids"]},
        delivered={name: {str(item) for item in ids} for name, ids in raw_delivered.items()},
    )


def read_seen(path: Path) -> set[str]:
    """Compatibility API for existing callers."""
    return read_state(path).seen_ids


def save_state(path: Path, state: SeenState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    payload = {
        "version": 2,
        "seen_ids": sorted(state.seen_ids),
        "delivered": {
            name: sorted(ids)
            for name, ids in sorted(state.delivered.items())
            if ids
        },
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def save_seen(path: Path, seen: set[str]) -> None:
    """Compatibility API for existing callers."""
    save_state(path, SeenState(set(seen), {}))


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
        # Baseline only currently eligible activities. This does not send history.
        save_state(state_path, SeenState({a.id for a in matched}, {}))
        output(f"First-run baseline saved ({len(matched)} matches). No notifications sent.")
        return Result(len(raw), len(matched), 0, initialized=True)

    state = read_state(state_path)
    new_matches = [a for a in matched if a.id not in state.seen_ids]
    channels = tuple(notifier.channels)
    notified = 0
    deliveries = 0

    for activity in new_matches:
        if not channels:
            output("[preview, no channel configured]\n" + render_activity(activity))
            continue

        for channel in channels:
            if activity.id in state.delivered.get(channel, set()):
                continue
            notifier.send_channel(channel, activity)
            state.delivered.setdefault(channel, set()).add(activity.id)
            save_state(state_path, state)  # Save after each confirmed channel receipt.
            deliveries += 1

        state.seen_ids.add(activity.id)
        for delivered_ids in state.delivered.values():
            delivered_ids.discard(activity.id)  # No need for receipts once complete.
        save_state(state_path, state)
        notified += 1
        output(f"Notified activity {activity.id}.")

    output(
        f"Fetched={len(raw)}, matched={len(matched)}, "
        f"new_matches={len(new_matches)}, completed={notified}, deliveries={deliveries}."
    )
    return Result(len(raw), len(matched), notified, deliveries=deliveries)
