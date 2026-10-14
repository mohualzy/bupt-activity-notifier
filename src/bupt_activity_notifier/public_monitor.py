"""Separate anonymous official-campus notices watcher.

Runs without student credentials. Output means 'unverified public lead', NEVER
a confirmed Second Classroom check-in activity. Uses the existing opt-in
ServerChan/OneBot notification configuration but no Second Classroom token.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable

import requests

from .notifications import Notifier, NotificationError
from .public_sources import (
    SOURCES, Lead, PublicFetchError, PublicSource, discover, read_candidate,
)


@dataclass(frozen=True)
class Summary:
    sources_ok: int = 0
    sources_failed: int = 0
    discovered: int = 0
    leads: int = 0
    delivered: int = 0
    initialized: int = 0


def _empty() -> dict:
    return {"version": 1, "sources": {}}


def read_public_state(path: Path) -> dict:
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError):
        raise ValueError("Public source state unreadable; refusing to reset deduplication.") from None
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Invalid public source state schema.")
    sources = data.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("Invalid public source ledger.")
    for source_name, entry in sources.items():
        if not isinstance(source_name, str) or not isinstance(entry, dict):
            raise ValueError("Invalid public source state.")
        if entry.get("initialized") is not True:
            raise ValueError("Uninitialized source in state.")
        if not isinstance(entry.get("seen"), list) or not all(isinstance(x, str) for x in entry["seen"]):
            raise ValueError("Invalid seen public source URLs.")
        delivered = entry.get("delivered", {})
        if not isinstance(delivered, dict) or not all(
            isinstance(channel, str)
            and isinstance(urls, list)
            and all(isinstance(url, str) for url in urls)
            for channel, urls in delivered.items()
        ):
            raise ValueError("Invalid public notification receipts.")
    return data


def save_public_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def lead_title(lead: Lead) -> str:
    return "北邮公开活动线索（非二课核验）"


def lead_body(lead: Lead) -> str:
    return (
        f"来源：{lead.source}\n"
        f"公开发布时间：{lead.published}\n"
        f"活动：{lead.title}\n"
        f"线索：{lead.reason}\n"
        f"原文：{lead.url}\n\n"
        "【注意】这是一条公开活动线索，并非第二课堂已核验活动。"
        "沙河举办地点、能否报名、是否需要签到和签退，须以官方活动页面为准。"
        "若第二课堂 Token 已过期，本通知依然可以发送，但可能漏报二课活动。"
    )


def run_public_poll(
    notifier: Notifier,
    state_path: Path,
    *,
    sources: tuple[PublicSource, ...] = SOURCES,
    session: requests.Session | None = None,
    output: Callable[[str], None] = print,
    dry_run: bool = False,
    max_candidates: int = 12,
) -> Summary:
    """On first successful GET per source, only establish a no-spam baseline."""
    state = read_public_state(state_path)
    session = session or requests.Session()
    state_sources = state["sources"]
    sources_ok = sources_failed = discovered = leads = delivered = initialized = 0
    attempted = 0

    for source in sources:
        try:
            listing = discover(source, session)
            if not listing:
                raise PublicFetchError("Public listing returned no recognized articles.")
        except PublicFetchError:
            sources_failed += 1
            output(f"Public source {source.name}: unavailable; state preserved.")
            continue

        sources_ok += 1
        discovered += len(listing)
        if source.name not in state_sources:
            initialized += 1
            output(f"Public source {source.name}: baseline={len(listing)}; no history sent.")
            if not dry_run:
                state_sources[source.name] = {
                    "initialized": True, "seen": sorted(listing),
                    "delivered": {},
                }
                save_public_state(state_path, state)
            continue

        entry = state_sources[source.name]
        seen = set(entry["seen"])
        receipts = {c: set(ids) for c, ids in entry.get("delivered", {}).items()}

        for url, listed_title in listing.items():
            if url in seen:
                continue
            if attempted >= max_candidates:
                break
            attempted += 1

            try:
                candidate = read_candidate(source, url, listed_title, session)
            except PublicFetchError:
                output(f"Public source {source.name}: new article temporarily unavailable.")
                continue

            if candidate is None:
                seen.add(url)
                if not dry_run:
                    entry["seen"] = sorted(seen)
                    save_public_state(state_path, state)
                continue

            leads += 1
            output(f"Public source {source.name}: new candidate article.")
            if dry_run:
                continue

            # Successful notification per channel gets an atomic receipt.
            for channel in notifier.channels:
                if url in receipts.get(channel, set()):
                    continue
                try:
                    notifier.send_notice_channel(
                        channel, lead_title(candidate), lead_body(candidate)
                    )
                except NotificationError:
                    output(f"Public lead delivery failed ({channel}); will retry.")
                    continue
                receipts.setdefault(channel, set()).add(url)
                entry["delivered"] = {
                    c: sorted(v) for c, v in receipts.items() if v
                }
                save_public_state(state_path, state)
                delivered += 1

            if notifier.channels and all(url in receipts.get(c, set()) for c in notifier.channels):
                seen.add(url)
                for values in receipts.values():
                    values.discard(url)
                entry["seen"] = sorted(seen)
                entry["delivered"] = {c: sorted(v) for c, v in receipts.items() if v}
                save_public_state(state_path, state)

    output(
        f"Public: sources_ok={sources_ok}, sources_failed={sources_failed}, "
        f"listed={discovered}, relevant_new={leads}, deliveries={delivered}, "
        f"baseline_sources={initialized}."
    )
    return Summary(sources_ok, sources_failed, discovered, leads, delivered, initialized)
