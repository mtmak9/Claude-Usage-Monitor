"""Higher-level history / activity queries built on top of :class:`Database`.

Turns raw snapshot rows into the arrays the overlay needs (hourly activity,
prompt timeline, prompt counts) and the records the history window charts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from ..api.models import ActivityData, DailyUsageRecord
from .database import Database


def _start_of_today_utc() -> datetime:
    local_now = datetime.now()
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc)


class HistoryService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    def compute_activity(self) -> ActivityData:
        """Derive activity arrays from real stored snapshots (today)."""
        start = _start_of_today_utc()
        rows = self.db.snapshots_since(start.isoformat())

        hourly = [0.0] * 24
        timeline: List[float] = []
        prev_requests = None
        prompts_today = 0

        for row in rows:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
            except (ValueError, TypeError):
                continue
            local = ts.astimezone()
            hour = local.hour
            frac = (local.hour * 3600 + local.minute * 60) / 86400.0

            # A "prompt" is inferred from a drop in requests_remaining.
            req = row["requests_remaining"]
            if prev_requests is not None and req is not None and req < prev_requests:
                prompts_today += 1
                timeline.append(frac)
                hourly[hour] += 1.0
            prev_requests = req if req is not None else prev_requests

        # Blend in the explicit daily prompt counter (covers app restarts).
        counter = self.db.prompt_count_for_date(datetime.now().strftime("%Y-%m-%d"))
        prompts_today = max(prompts_today, counter)

        peak = max(hourly) if any(hourly) else 1.0
        hourly = [round(v / peak, 3) for v in hourly]

        return ActivityData(
            prompts_today=prompts_today,
            prompts_week=self._prompts_in_days(7),
            prompts_month=self._prompts_in_days(30),
            timeline=sorted(timeline),
            hourly=hourly,
        )

    def _prompts_in_days(self, days: int) -> int:
        total = 0
        today = datetime.now()
        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            total += self.db.prompt_count_for_date(date)
        return total

    # ------------------------------------------------------------------ #
    def daily_records(self, days: int = 14) -> List[DailyUsageRecord]:
        rows = self.db.daily_summaries(limit=days)
        records: List[DailyUsageRecord] = []
        for row in rows:
            records.append(
                DailyUsageRecord(
                    date=row["date"],
                    total_prompts=int(row["total_prompts"] or 0),
                    peak_session_util=float(row["peak_session_util"] or 0),
                    peak_week_util=float(row["peak_week_util"] or 0),
                )
            )
        records.reverse()  # chronological for charting
        return records

    def session_util_series(self, hours: int = 24) -> List[tuple]:
        """Return [(datetime, session_util), ...] for the last N hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = self.db.snapshots_since(since.isoformat())
        series = []
        for row in rows:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
            except (ValueError, TypeError):
                continue
            series.append((ts, float(row["session_util"] or 0)))
        return series
