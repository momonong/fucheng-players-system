"""Calendar schedule shared by the backup worker and the admin status view."""
from datetime import datetime, timedelta, time as clock_time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def taipei_zone():
    try:
        return ZoneInfo("Asia/Taipei")
    except ZoneInfoNotFoundError:
        # Windows synthetic tests may lack tzdata; Taiwan currently uses UTC+08.
        return timezone(timedelta(hours=8), "Asia/Taipei")


def latest_weekly_due(now: datetime) -> datetime:
    local = now.astimezone(taipei_zone())
    monday = local.date() - timedelta(days=local.weekday())
    due = datetime.combine(monday, clock_time(4), taipei_zone())
    if local < due:
        due -= timedelta(days=7)
    return due
