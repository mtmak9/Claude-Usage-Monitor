"""Data models shared between the API layer, storage and the UI.

These are plain dataclasses with a few computed helpers so the UI never has to
do arithmetic on raw header values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


@dataclass
class UsageSnapshot:
    """A single point-in-time reading of Claude usage / rate limits."""

    timestamp: datetime = field(default_factory=_now)
    model: str = "claude-opus-4-8"

    # --- Request rate limits ------------------------------------------- #
    requests_limit: Optional[int] = None
    requests_remaining: Optional[int] = None
    requests_reset: Optional[datetime] = None

    # --- Token rate limits --------------------------------------------- #
    tokens_limit: Optional[int] = None
    tokens_remaining: Optional[int] = None
    input_tokens_limit: Optional[int] = None
    input_tokens_remaining: Optional[int] = None
    output_tokens_limit: Optional[int] = None
    output_tokens_remaining: Optional[int] = None
    tokens_reset: Optional[datetime] = None

    # --- Subscription / OAuth utilisation (0-100) ---------------------- #
    session_utilization: float = 0.0    # rolling 5h window
    week_utilization: float = 0.0       # rolling 7d window
    opus_week_utilization: float = 0.0  # 7d window for Opus specifically
    session_reset: Optional[datetime] = None
    week_reset: Optional[datetime] = None

    # --- Subscription metadata ----------------------------------------- #
    subscription_percent: float = 0.0   # overall cycle usage 0-100
    plan_name: str = "—"
    cycle_label: str = "—"
    cycle_renews: Optional[datetime] = None

    # --- Usage credits ($) --------------------------------------------- #
    credits_enabled: bool = False
    credits_used: Optional[float] = None      # dollars spent this cycle
    credits_limit: Optional[float] = None     # monthly spend limit (dollars)
    credits_balance: Optional[float] = None   # current balance (dollars)
    credits_percent: float = 0.0              # 0-100 of the limit used
    credits_currency: str = "USD"
    credits_can_purchase: bool = False

    # --- Context flags ------------------------------------------------- #
    is_peak: bool = False
    is_mock: bool = False
    is_stale: bool = False   # last good data re-shown (e.g. after a 429)
    error: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Computed helpers
    # ------------------------------------------------------------------ #
    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def session_percent(self) -> float:
        if self.session_utilization:
            return _clamp(self.session_utilization)
        return self._requests_percent()

    @property
    def week_percent(self) -> float:
        if self.week_utilization:
            return _clamp(self.week_utilization)
        return self._requests_percent()

    def _requests_percent(self) -> float:
        if self.requests_limit and self.requests_remaining is not None:
            used = self.requests_limit - self.requests_remaining
            return _clamp(used / self.requests_limit * 100.0)
        return 0.0

    @property
    def tokens_percent(self) -> float:
        if self.tokens_limit and self.tokens_remaining is not None:
            used = self.tokens_limit - self.tokens_remaining
            return _clamp(used / self.tokens_limit * 100.0)
        return 0.0

    @property
    def worst_percent(self) -> float:
        """The highest utilisation across windows — drives icon colour."""
        return max(self.session_percent, self.week_percent, self.tokens_percent)

    @staticmethod
    def _format_delta(target: Optional[datetime]) -> str:
        if not target:
            return "—"
        delta = target - _now()
        seconds = int(delta.total_seconds())
        if seconds <= 0:
            return "teraz"
        hours, rem = divmod(seconds, 3600)
        minutes = rem // 60
        if hours >= 24:
            days = hours // 24
            return f"za {days}d {hours % 24}h"
        if hours > 0:
            return f"za {hours}h {minutes}m"
        return f"za {minutes}m"

    @property
    def session_reset_text(self) -> str:
        return self._format_delta(self.session_reset)

    @property
    def week_reset_text(self) -> str:
        return self._format_delta(self.week_reset)

    @property
    def cycle_renews_text(self) -> str:
        return self._format_delta(self.cycle_renews)

    # -- credits -------------------------------------------------------- #
    @staticmethod
    def _fmt_money(value: Optional[float], currency: str = "USD") -> str:
        if value is None:
            return "—"
        symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency.upper(), "")
        return f"{symbol}{value:,.2f}" if symbol else f"{value:,.2f} {currency}"

    @property
    def credits_used_text(self) -> str:
        return self._fmt_money(self.credits_used, self.credits_currency)

    @property
    def credits_limit_text(self) -> str:
        return self._fmt_money(self.credits_limit, self.credits_currency)

    @property
    def credits_balance_text(self) -> str:
        return self._fmt_money(self.credits_balance, self.credits_currency)


@dataclass
class SubscriptionInfo:
    """Higher-level subscription / plan description (best-effort)."""

    plan_name: str = "—"
    status: str = "—"
    cycle_label: str = "—"
    renews: Optional[datetime] = None
    used_percent: float = 0.0
    remaining_label: str = "—"


@dataclass
class DailyUsageRecord:
    """Aggregated usage for a single calendar day (history view)."""

    date: str  # ISO date "YYYY-MM-DD"
    total_prompts: int = 0
    peak_session_util: float = 0.0
    peak_week_util: float = 0.0
    avg_session_util: float = 0.0


@dataclass
class ActivityData:
    """Prompt counts and activity shape used by the overlay's PROMPTY /
    AKTYWNOŚĆ sections."""

    prompts_today: int = 0
    prompts_week: int = 0
    prompts_month: int = 0
    timeline: list = field(default_factory=list)   # fractions 0-1 across today
    hourly: list = field(default_factory=list)     # length 24, intensity 0-1

    def prompts_for_tab(self, tab_index: int) -> int:
        return {0: self.prompts_today, 1: self.prompts_week, 2: self.prompts_month}.get(
            tab_index, self.prompts_today
        )
