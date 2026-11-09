from datetime import date, datetime, time, timedelta, timezone
import re

from .time_utils import format_hour, get_timezone


DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_RANGE = re.compile(r"^(\\d{1,2})\\s*-\\s*(\\d{1,2})$")


def parse_schedule_fields(fields: dict[str, str]) -> list[dict]:
    intervals = []
    for key, raw_value in fields.items():
        day_key, status = key.rsplit("_", 1)
        weekday = DAY_KEYS.index(day_key)
        for part in (raw_value or "").split(","):
            part = part.strip()
            if not part:
                continue
            match = _RANGE.fullmatch(part)
            if not match:
                raise ValueError(
                    f"Invalid range '{part}'. Use whole hours, e.g. 09-14, 18-21."
                )
            start_hour, end_hour = map(int, match.groups())
            if start_hour > 23 or end_hour > 24 or start_hour == end_hour:
                raise ValueError(
                    f"Invalid range '{part}'. Start must be 00-23 and end 00-24."
                )
            if end_hour > start_hour:
                intervals.append({
                    "weekday": weekday, "status": status,
                    "start_hour": start_hour, "end_hour": end_hour,
                })
            else:
                intervals.append({
                    "weekday": weekday, "status": status,
                    "start_hour": start_hour, "end_hour": 24,
                })
                if end_hour > 0:
                    intervals.append({
                        "weekday": (weekday + 1) % 7, "status": status,
                        "start_hour": 0, "end_hour": end_hour,
                    })
    validate_intervals(intervals)
    return intervals


def validate_intervals(intervals: list[dict]) -> None:
    by_day = {}
    for item in intervals:
        by_day.setdefault(int(item["weekday"]), []).append(item)
    for weekday, day_items in by_day.items():
        ordered = sorted(day_items, key=lambda item: item["start_hour"])
        for previous, current in zip(ordered, ordered[1:]):
            if current["start_hour"] < previous["end_hour"]:
                raise ValueError(
                    f"Free and Chat-only ranges overlap on {DAYS[weekday]}. "
                    "Please remove the overlap."
                )


def matching_interval(intervals: list[dict], local_time: datetime) -> dict | None:
    for item in intervals:
        if (
            int(item["weekday"]) == local_time.weekday()
            and int(item["start_hour"]) <= local_time.hour < int(item["end_hour"])
        ):
            return item
    return None


def current_status(intervals: list[dict], local_time: datetime):
    item = matching_interval(intervals, local_time)
    return (item["status"], item) if item else (None, None)


def format_interval(item: dict) -> str:
    start = datetime(2000, 1, 1, int(item["start_hour"]))
    end_hour = int(item["end_hour"])
    end = datetime(2000, 1, 2, 0) if end_hour == 24 else datetime(2000, 1, 1, end_hour)
    return f"{format_hour(start)}–{format_hour(end)}"


def weekly_hours(
    profiles: list[dict], requester_timezone: str, weekday: int,
    now_utc: datetime | None = None,
):
    requester_tz = get_timezone(requester_timezone)
    now = now_utc or datetime.now(timezone.utc)
    requester_today = now.astimezone(requester_tz).date()
    target_date: date = requester_today + timedelta(
        days=(weekday - requester_today.weekday()) % 7
    )

    rows = []
    for hour in range(24):
        slot = datetime.combine(target_date, time(hour=hour), tzinfo=requester_tz)
        utc_slot = slot.astimezone(timezone.utc)
        free_count = 0
        chat_count = 0

        for profile in profiles:
            member_local = utc_slot.astimezone(get_timezone(profile["timezone"]))
            status, _ = current_status(profile["intervals"], member_local)
            if status == "free":
                free_count += 1
            elif status == "chat":
                chat_count += 1

        if free_count >= 3:
            color = "🟩"
        elif free_count in (1, 2) or chat_count >= 2:
            color = "🟨"
        elif free_count == 0 and chat_count == 0 and hour < 12:
            color = "⬛"
        else:
            color = "🟥"

        rows.append({
            "hour": slot, "free": free_count, "chat": chat_count, "color": color,
        })
    return target_date, rows
