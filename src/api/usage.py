"""Parse the ``GET /api/oauth/usage`` response into a :class:`UsageSnapshot`.

The endpoint (subscription / OAuth only) returns JSON shaped like::

    {
      "five_hour":  {"utilization": 18.0, "resets_at": "2026-06-26T14:50:00+00:00", …},
      "seven_day":  {"utilization": 4.0,  "resets_at": "2026-07-02T23:00:00+00:00", …},
      "seven_day_opus":   null,
      "seven_day_sonnet": {"utilization": 0.0, "resets_at": "…", …},
      "limits": [
        {"kind": "session",       "group": "session", "percent": 18, "is_active": true,  "resets_at": "…"},
        {"kind": "weekly_all",    "group": "weekly",  "percent": 4,  "is_active": false, "resets_at": "…"},
        {"kind": "weekly_scoped", "group": "weekly",  "percent": 0,  "is_active": false, "resets_at": "…",
         "scope": {"model": {"display_name": "Sonnet"}}}
      ],
      "extra_usage": {"is_enabled": false, …},
      "spend": {…},
      …many nullable, code-named buckets we ignore…
    }

``utilization`` / ``percent`` are already 0–100 percentages.  Every field is
treated as optional so partial / evolving payloads never crash the UI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .models import UsageSnapshot

log = logging.getLogger(__name__)


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # The endpoint reports 0–100 already; clamp defensively.
    return max(0.0, min(100.0, v))


def _to_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        iso = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _window(data: Mapping[str, Any], key: str) -> tuple[Optional[float], Optional[datetime]]:
    node = data.get(key)
    if not isinstance(node, Mapping):
        return None, None
    return _to_float(node.get("utilization")), _to_dt(node.get("resets_at"))


def _money(value: Any) -> Optional[float]:
    """Normalise a money field to a float in major units (e.g. dollars).

    Handles both ``{"amount_minor": 1234, "exponent": 2}`` objects and bare
    numbers; returns ``None`` for anything missing.
    """
    if value is None:
        return None
    if isinstance(value, Mapping):
        minor = value.get("amount_minor")
        if minor is None:
            return None
        try:
            return float(minor) / (10 ** int(value.get("exponent", 2)))
        except (TypeError, ValueError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _currency_of(*candidates: Any) -> str:
    for c in candidates:
        if isinstance(c, Mapping) and c.get("currency"):
            return str(c["currency"])
        if isinstance(c, str) and c:
            return c
    return "USD"


def _apply_credits(data: Mapping[str, Any], snap: UsageSnapshot) -> None:
    """Populate the credit ($) fields from the ``spend`` / ``extra_usage`` blocks."""
    spend = data.get("spend") if isinstance(data.get("spend"), Mapping) else {}
    extra = data.get("extra_usage") if isinstance(data.get("extra_usage"), Mapping) else {}

    snap.credits_enabled = bool(spend.get("enabled") or extra.get("is_enabled"))
    snap.credits_used = _money(spend.get("used"))
    if snap.credits_used is None:
        snap.credits_used = _money(extra.get("used_credits"))
    snap.credits_limit = _money(spend.get("limit"))
    if snap.credits_limit is None:
        snap.credits_limit = _money(extra.get("monthly_limit"))
    snap.credits_balance = _money(spend.get("balance"))
    snap.credits_percent = (
        _to_float(spend.get("percent")) or _to_float(extra.get("utilization")) or 0.0
    )
    snap.credits_currency = _currency_of(
        spend.get("used"), spend.get("limit"), extra.get("currency")
    )
    snap.credits_can_purchase = bool(spend.get("can_purchase_credits"))


def parse_oauth_usage(
    data: Mapping[str, Any],
    *,
    model: str,
    plan_name: str = "—",
    is_peak: bool = False,
) -> UsageSnapshot:
    """Build a :class:`UsageSnapshot` from a parsed usage-endpoint payload."""
    snap = UsageSnapshot(
        timestamp=datetime.now(timezone.utc), model=model, is_peak=is_peak
    )

    five_util, five_reset = _window(data, "five_hour")
    seven_util, seven_reset = _window(data, "seven_day")
    opus_util, _ = _window(data, "seven_day_opus")
    sonnet_util, _ = _window(data, "seven_day_sonnet")

    if five_util is not None:
        snap.session_utilization = five_util
    if seven_util is not None:
        snap.week_utilization = seven_util
    # Opus-specific weekly window; fall back to the scoped Sonnet number so the
    # third bar isn't dead when no Opus usage has been recorded yet.
    if opus_util is not None:
        snap.opus_week_utilization = opus_util
    elif sonnet_util is not None:
        snap.opus_week_utilization = sonnet_util

    snap.session_reset = five_reset
    snap.week_reset = seven_reset

    # The usage endpoint has no monthly billing cycle, so the overlay's third
    # gauge tracks the 7-day subscription window (the real Max/Pro limit).
    snap.plan_name = plan_name
    snap.subscription_percent = snap.week_utilization
    snap.cycle_label = plan_name
    snap.cycle_renews = seven_reset

    # ``limits`` is the authoritative, forward-compatible list — let it override
    # the convenience windows above when present (e.g. future limit kinds).
    for limit in data.get("limits") or []:
        if not isinstance(limit, Mapping):
            continue
        pct = _to_float(limit.get("percent"))
        reset = _to_dt(limit.get("resets_at"))
        group = (limit.get("group") or limit.get("kind") or "").lower()
        if group == "session" and pct is not None:
            snap.session_utilization = pct
            if reset:
                snap.session_reset = reset
        elif group == "weekly" and (limit.get("kind") == "weekly_all") and pct is not None:
            snap.week_utilization = pct
            snap.subscription_percent = pct
            if reset:
                snap.week_reset = reset
                snap.cycle_renews = reset

    _apply_credits(data, snap)
    return snap
