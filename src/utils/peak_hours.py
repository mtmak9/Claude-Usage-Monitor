"""Peak / off-peak hour calculations in US Pacific time.

Anthropic's heavy-traffic window is roughly business hours on the US west
coast.  We treat 09:00-18:00 Pacific on weekdays as *peak* and everything else
as *off-peak*.  All maths is done in Pacific local time (DST-aware via
``zoneinfo``) and gracefully degrades to a fixed UTC-8 offset if the tz
database is unavailable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from .. import constants
from ..i18n import tr

try:  # zoneinfo ships with Python 3.9+, tzdata provides the database on Windows
    from zoneinfo import ZoneInfo

    _PACIFIC = ZoneInfo(constants.PEAK_TIMEZONE)
except Exception:  # pragma: no cover - fallback when tzdata missing
    _PACIFIC = timezone(timedelta(hours=-8))  # PST, no DST


def to_pacific(dt: datetime | None = None) -> datetime:
    """Convert (or take now) to Pacific local time."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_PACIFIC)


def is_peak(dt: datetime | None = None) -> bool:
    """Return True if the given moment falls inside the peak window."""
    local = to_pacific(dt)
    if constants.PEAK_WEEKDAYS_ONLY and local.weekday() >= 5:  # 5,6 == Sat,Sun
        return False
    return constants.PEAK_START_HOUR <= local.hour < constants.PEAK_END_HOUR


def peak_label(dt: datetime | None = None) -> str:
    return "PEAK" if is_peak(dt) else "OFF-PEAK"


def current_pacific_hour_fraction(dt: datetime | None = None) -> float:
    """Return the current position in the 24h day as a 0.0-1.0 fraction.

    Used to draw the "now" marker on the 24-hour peak indicator bar.
    """
    local = to_pacific(dt)
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    return seconds / 86400.0


def hour_is_peak(hour: int) -> bool:
    """Is a given clock hour (0-23, Pacific) inside the peak window?

    Note: this ignores weekday/weekend so the 24h strip is stable to look at.
    """
    return constants.PEAK_START_HOUR <= hour < constants.PEAK_END_HOUR


def peak_segments() -> List[dict]:
    """Return drawable segments describing the 24h day.

    Each segment: {"start": 0-1, "end": 0-1, "peak": bool}
    """
    segments: List[dict] = []
    start = 0
    current = hour_is_peak(0)
    for hour in range(1, 25):
        is_p = hour_is_peak(hour) if hour < 24 else not current  # force close at 24
        if hour == 24 or is_p != current:
            segments.append(
                {"start": start / 24.0, "end": hour / 24.0, "peak": current}
            )
            start = hour
            current = is_p
    return segments


def next_transition_text(dt: datetime | None = None) -> str:
    """Human text describing when peak/off-peak status next flips."""
    local = to_pacific(dt)
    currently_peak = is_peak(dt)
    if currently_peak:
        target = local.replace(
            hour=constants.PEAK_END_HOUR, minute=0, second=0, microsecond=0
        )
        verb = tr("peak_verb_off")
    else:
        if local.hour < constants.PEAK_START_HOUR:
            target = local.replace(
                hour=constants.PEAK_START_HOUR, minute=0, second=0, microsecond=0
            )
        else:
            target = (local + timedelta(days=1)).replace(
                hour=constants.PEAK_START_HOUR, minute=0, second=0, microsecond=0
            )
        verb = tr("peak_verb_peak")
    delta = target - local
    seconds = max(0, int(delta.total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours > 0:
        return tr("peak_in_hm", verb=verb, h=hours, m=minutes)
    return tr("peak_in_m", verb=verb, m=minutes)
