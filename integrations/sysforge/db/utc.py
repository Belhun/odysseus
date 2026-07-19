"""UTC storage and local display helpers for Business DB timestamps.

Rule: all Business DB timestamps are UTC TEXT ``yyyy-MM-dd HH:mm:ss``.
Convert to local only at UI / JSON response formatting.

Do not confuse with ``src.user_time`` (chat relative dates).
"""

from __future__ import annotations

from datetime import datetime, timezone


STORAGE_FORMAT = "%Y-%m-%d %H:%M:%S"
DISPLAY_DATE = "%m/%d/%Y"
DISPLAY_DATETIME = "%m/%d/%Y %I:%M %p"
DISPLAY_TIME = "%I:%M %p"


def utc_now() -> datetime:
    """Current time as timezone-aware UTC."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Ensure UTC. Aware non-UTC converts; naive is treated as local → UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    # Naive: treat as local (matches DateTimeHelpers.ToUtc unspecified→Local→UTC)
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
    return dt.replace(tzinfo=local_tz).astimezone(timezone.utc)


def format_storage(dt: datetime | None = None) -> str:
    """Format for DB TEXT storage: ``yyyy-MM-dd HH:mm:ss`` UTC."""
    if dt is None:
        dt = utc_now()
    else:
        dt = to_utc(dt)
    return dt.strftime(STORAGE_FORMAT)


def parse_storage(text: str) -> datetime:
    """Parse DB TEXT as UTC (naive string → assume UTC)."""
    raw = text.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    dt = datetime.strptime(raw, STORAGE_FORMAT)
    return dt.replace(tzinfo=timezone.utc)


def to_local(utc_dt: datetime) -> datetime:
    """Convert UTC timestamp to local time for display."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    elif utc_dt.tzinfo != timezone.utc:
        # Already local-aware with a different zone — return as local wall time
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        if utc_dt.tzinfo == local_tz:
            return utc_dt
        utc_dt = utc_dt.astimezone(timezone.utc)
    return utc_dt.astimezone()


def format_date(utc_dt: datetime) -> str:
    """Local display date: ``12/20/2024``."""
    return to_local(utc_dt).strftime(DISPLAY_DATE)


def format_datetime(utc_dt: datetime) -> str:
    """Local display datetime: ``12/20/2024 5:30 PM``."""
    local = to_local(utc_dt)
    hour = local.strftime("%I").lstrip("0") or "0"
    return f"{local.strftime(DISPLAY_DATE)} {hour}:{local.strftime('%M %p')}"


def format_time(utc_dt: datetime) -> str:
    """Local display time: ``5:30 PM``."""
    local = to_local(utc_dt)
    hour = local.strftime("%I").lstrip("0") or "0"
    return f"{hour}:{local.strftime('%M %p')}"


def format_relative(utc_dt: datetime, now: datetime | None = None) -> str:
    """Relative local time: ``2 hours ago``, ``Yesterday``, etc."""
    local = to_local(utc_dt)
    if now is None:
        now = datetime.now().astimezone()
    elif now.tzinfo is None:
        now = now.astimezone()
    else:
        now = now.astimezone()

    diff = now - local.astimezone(now.tzinfo)

    if diff.total_seconds() < 60:
        return "Just now"
    if diff.total_seconds() < 3600:
        return f"{int(diff.total_seconds() // 60)} min ago"
    if diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() // 3600)
        return f"{hours} hours ago"
    if diff.days < 2:
        return "Yesterday"
    if diff.days < 7:
        return f"{diff.days} days ago"
    return format_date(utc_dt)


def format_title_with_date(name: str, utc_dt: datetime) -> str:
    """Display title with local date: ``John Doe - 12/20/2024``."""
    return f"{name} - {format_date(utc_dt)}"


def validate_utc(dt: datetime, param_name: str = "DateTime") -> None:
    """Raise ValueError if dt is not timezone-aware UTC."""
    offset = dt.utcoffset() if dt.tzinfo is not None else None
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(
            f"{param_name} must be in UTC. Use utc_now() or to_utc() to ensure UTC."
        )


def ensure_utc(dt: datetime) -> datetime:
    """Ensure UTC, converting if necessary."""
    return to_utc(dt)
