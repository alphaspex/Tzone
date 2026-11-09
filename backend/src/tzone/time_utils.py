from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re


_SUFFIX = re.compile(r"\s+\|\s+\d{1,2}\s+(?:AM|PM)$", re.IGNORECASE)


def get_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Use a valid IANA timezone, such as Africa/Algiers.") from exc


def format_hour(value: datetime) -> str:
    return value.strftime("%I %p").lstrip("0")


def nickname_for(server_name: str, local_hour: datetime) -> str:
    base = _SUFFIX.sub("", server_name).strip()
    suffix = " | " + format_hour(local_hour)
    return (base[: 32 - len(suffix)].rstrip() or "Member") + suffix


def due_cycle(local_now: datetime, window_minutes: int = 10):
    if local_now.minute >= 60 - window_minutes:
        cycle_hour = local_now.replace(minute=0, second=0, microsecond=0)
        return cycle_hour.strftime("%Y-%m-%d-%H"), cycle_hour + timedelta(hours=1)
    if local_now.minute < 5:
        display_hour = local_now.replace(minute=0, second=0, microsecond=0)
        cycle_hour = display_hour - timedelta(hours=1)
        return cycle_hour.strftime("%Y-%m-%d-%H"), display_hour
    return None
