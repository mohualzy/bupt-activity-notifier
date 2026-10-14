"""Shahe campus selection and attendance details from observed UI fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


def matches_shahe(activity: Activity) -> bool:
    """Only the explicitly identified Shahe campus is eligible.

    Attendance requirements are shown in the notification but never used
    to exclude an activity. Unknown campus remains ineligible.
    """
    return activity.area == 1


BEIJING_TIME = timezone(timedelta(hours=8))


def _display_time(value: str) -> tuple[str, bool]:
    """Convert explicit UTC/offset timestamps, but never guess naive timezones."""
    if not value:
        return "", False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value, False
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return value, False
    local_time = parsed.astimezone(BEIJING_TIME)
    return local_time.strftime("%Y-%m-%d %H:%M"), True


def _markdown_safe(value: str) -> str:
    """Treat university-supplied text as text, not Markdown/HTML syntax."""
    import re

    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", value)


def _requirement(activity: Activity, flag: int, label: str) -> str:
    requires = activity.requires(flag)
    if requires is None:
        return f"{label}未知"
    return f"需{label}" if requires else f"无需{label}"


def render_activity(activity: Activity) -> str:
    """ServerChan-compatible Markdown: separate title, fields and times."""
    start, start_converted = _display_time(activity.start)
    end, end_converted = _display_time(activity.end)
    start_label = "开始时间（北京时间）" if start_converted else "开始时间"
    end_label = "结束时间（北京时间）" if end_converted else "结束时间"

    return "\n".join((
        f"### {_markdown_safe(activity.title)}",
        "",
        f"- **校区**：{_markdown_safe(activity.area_label)}",
        f"- **地点**：{_markdown_safe(activity.location or '未公布')}",
        f"- **{start_label}**：{_markdown_safe(start or '未公布')}",
        f"- **{end_label}**：{_markdown_safe(end or '未公布')}",
        "",
        f"- **报名**：{_requirement(activity, SIGN_UP, '报名')}",
        f"- **签到**：{_requirement(activity, CHECK_IN, '签到')}",
        f"- **签退**：{_requirement(activity, CHECK_OUT, '签退')}",
        f"- **活动 ID**：`{_markdown_safe(activity.id)}`",
    ))
