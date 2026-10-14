"""Explicit attendance flags and campus enum, derived from observed UI logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

AREA_NAMES = {
    0: "西土城校区",
    1: "沙河校区",
    2: "线上",
    3: "海南校区",
    100000000: "其他",
}
SIGN_UP = 1
CHECK_IN = 2
CHECK_OUT = 4


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class Activity:
    id: str
    title: str
    area: int | None
    demands: int | None
    location: str
    start: str
    end: str

    @classmethod
    def from_raw(cls, data: Mapping[str, Any]) -> "Activity":
        raw_id = data.get("id")
        if raw_id is None or str(raw_id) == "":
            raise ValueError("Activity record is missing id.")
        return cls(
            id=str(raw_id),
            title=str(data.get("name") or data.get("activity_name") or "(未命名活动)"),
            area=_int_or_none(data.get("area")),
            demands=_int_or_none(data.get("demands")),
            location=str(data.get("location") or ""),
            start=str(data.get("activity_start_time") or ""),
            end=str(data.get("activity_end_time") or ""),
        )

    @property
    def area_label(self) -> str:
        return AREA_NAMES.get(self.area, "未确认校区")

    def requires(self, bit: int) -> bool | None:
        if self.demands is None or self.demands < 0:
            return None
        return bool(self.demands & bit)


def matches_shahe_checkin_no_checkout(activity: Activity) -> bool:
    """Fail closed: missing/unknown flags are never interpreted as no check-out."""
    return (
        activity.area == 1
        and activity.requires(CHECK_IN) is True
        and activity.requires(CHECK_OUT) is False
    )


def render_activity(activity: Activity) -> str:
    signup = activity.requires(SIGN_UP)
    signup_label = "需报名" if signup else "不报名" if signup is False else "报名未知"
    return (
        f"{activity.title}\n"
        f"校区：{activity.area_label} {activity.location}\n"
        f"时间：{activity.start} 至 {activity.end}\n"
        f"要求：{signup_label} / 需签到 / 不签退\n"
        f"活动 ID：{activity.id}"
    )
