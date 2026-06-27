"""Parsing of ``anthropic-ratelimit-*`` response headers into a UsageSnapshot.

The Anthropic API returns a family of rate-limit headers on every response:

    anthropic-ratelimit-requests-limit / -remaining / -reset
    anthropic-ratelimit-tokens-limit / -remaining / -reset
    anthropic-ratelimit-input-tokens-*  / -output-tokens-*

OAuth / subscription responses additionally expose utilisation percentages such
as ``anthropic-ratelimit-unified-5h-utilization`` (rolling session window) and
``-7d-utilization`` (weekly window).  We parse whatever subset is present and
leave the rest as ``None``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Mapping, Optional

from .models import UsageSnapshot

log = logging.getLogger(__name__)


def _get(headers: Mapping[str, str], *names: str) -> Optional[str]:
    """Case-insensitive lookup over several candidate header names."""
    lower = {k.lower(): v for k, v in headers.items()}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
        # Some utilisation headers are 0-1 fractions, others 0-100.
        return v * 100.0 if 0.0 <= v <= 1.0 else v
    except (TypeError, ValueError):
        return None


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a reset header that may be ISO-8601 or epoch seconds."""
    if value is None:
        return None
    value = value.strip()
    # Epoch seconds?
    try:
        if value.isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass
    # ISO-8601 (handle trailing Z)
    try:
        iso = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    # Relative seconds (e.g. "59s" or "120")
    try:
        secs = int("".join(ch for ch in value if ch.isdigit()))
        from datetime import timedelta

        return datetime.now(timezone.utc) + timedelta(seconds=secs)
    except (ValueError, OverflowError):
        return None


def parse_rate_limit_headers(
    headers: Mapping[str, str],
    *,
    model: str,
    is_peak: bool = False,
) -> UsageSnapshot:
    """Build a :class:`UsageSnapshot` from response headers."""
    snap = UsageSnapshot(timestamp=datetime.now(timezone.utc), model=model, is_peak=is_peak)

    # Requests
    snap.requests_limit = _to_int(_get(headers, "anthropic-ratelimit-requests-limit"))
    snap.requests_remaining = _to_int(
        _get(headers, "anthropic-ratelimit-requests-remaining")
    )
    snap.requests_reset = _to_datetime(
        _get(headers, "anthropic-ratelimit-requests-reset")
    )

    # Tokens (combined)
    snap.tokens_limit = _to_int(_get(headers, "anthropic-ratelimit-tokens-limit"))
    snap.tokens_remaining = _to_int(
        _get(headers, "anthropic-ratelimit-tokens-remaining")
    )
    snap.tokens_reset = _to_datetime(_get(headers, "anthropic-ratelimit-tokens-reset"))

    # Input / output tokens
    snap.input_tokens_limit = _to_int(
        _get(headers, "anthropic-ratelimit-input-tokens-limit")
    )
    snap.input_tokens_remaining = _to_int(
        _get(headers, "anthropic-ratelimit-input-tokens-remaining")
    )
    snap.output_tokens_limit = _to_int(
        _get(headers, "anthropic-ratelimit-output-tokens-limit")
    )
    snap.output_tokens_remaining = _to_int(
        _get(headers, "anthropic-ratelimit-output-tokens-remaining")
    )

    # Subscription / OAuth utilisation windows
    session = _to_float(
        _get(
            headers,
            "anthropic-ratelimit-unified-5h-utilization",
            "anthropic-ratelimit-5h-utilization",
            "anthropic-ratelimit-session-utilization",
        )
    )
    week = _to_float(
        _get(
            headers,
            "anthropic-ratelimit-unified-7d-utilization",
            "anthropic-ratelimit-7d-utilization",
            "anthropic-ratelimit-week-utilization",
        )
    )
    opus_week = _to_float(
        _get(
            headers,
            "anthropic-ratelimit-unified-7d-opus-utilization",
            "anthropic-ratelimit-7d-opus-utilization",
        )
    )
    if session is not None:
        snap.session_utilization = session
    if week is not None:
        snap.week_utilization = week
    if opus_week is not None:
        snap.opus_week_utilization = opus_week

    snap.session_reset = _to_datetime(
        _get(
            headers,
            "anthropic-ratelimit-unified-5h-reset",
            "anthropic-ratelimit-5h-reset",
        )
    )
    snap.week_reset = _to_datetime(
        _get(
            headers,
            "anthropic-ratelimit-unified-7d-reset",
            "anthropic-ratelimit-7d-reset",
        )
    )

    return snap
