"""Read Codex usage and rate-limit data from local Codex session logs.

Codex writes JSONL session records under ``~/.codex/sessions``. Recent records
include a technical ``payload.rate_limits`` object with primary/secondary window
utilisation and reset times, and ``payload.info.last_token_usage`` for local
token accounting. This module reads only those structured fields and ignores
message text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .. import constants
from .token_usage import TokenUsage


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


@dataclass
class CodexRateLimits:
    session_percent: float = 0.0
    week_percent: float = 0.0
    session_reset: Optional[datetime] = None
    week_reset: Optional[datetime] = None
    plan_type: str = "codex"
    limit_id: str = "codex"
    updated_at: Optional[datetime] = None

    @property
    def plan_label(self) -> str:
        plan = (self.plan_type or "codex").replace("_", " ").strip().title()
        return f"Codex {plan}" if plan.lower() != "codex" else "Codex"


class CodexUsageReader:
    """Best-effort reader for local Codex rate limits and token usage."""

    def __init__(self, sessions_root: Path | None = None) -> None:
        self.sessions_root = sessions_root or constants.CODEX_SESSIONS_DIR
        self._token_cache_key: tuple[int, int] | None = None
        self._token_cache: TokenUsage | None = None

    def _session_files(self) -> list[Path]:
        try:
            files = [
                p
                for p in self.sessions_root.rglob("*.jsonl")
                if p.is_file() and p.stat().st_size > 0
            ]
        except Exception:
            return []
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def available(self) -> bool:
        return bool(self._session_files())

    def latest_limits(self, max_files: int = 120) -> Optional[CodexRateLimits]:
        """Return the newest Codex rate-limit object found in session logs."""
        best: tuple[datetime, CodexRateLimits] | None = None
        for path in self._session_files()[:max_files]:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        payload = event.get("payload")
                        if not isinstance(payload, dict):
                            continue
                        raw = payload.get("rate_limits")
                        if not isinstance(raw, dict):
                            continue
                        parsed = self._parse_rate_limits(raw)
                        if not parsed:
                            continue
                        parsed.updated_at = _parse_ts(event.get("timestamp")) or parsed.updated_at
                        stamp = parsed.updated_at or datetime.fromtimestamp(
                            path.stat().st_mtime, tz=timezone.utc
                        )
                        if best is None or stamp > best[0]:
                            best = (stamp, parsed)
            except Exception:
                continue
        return best[1] if best else None

    def _parse_rate_limits(self, raw: dict[str, Any]) -> Optional[CodexRateLimits]:
        primary = raw.get("primary")
        secondary = raw.get("secondary")
        if not isinstance(primary, dict) and not isinstance(secondary, dict):
            return None
        now = _now()

        def pct(node: Any) -> float:
            if not isinstance(node, dict):
                return 0.0
            try:
                return max(0.0, min(100.0, float(node.get("used_percent") or 0.0)))
            except (TypeError, ValueError):
                return 0.0

        def reset(node: Any) -> Optional[datetime]:
            if not isinstance(node, dict):
                return None
            return _parse_ts(node.get("resets_at"))

        def window(node: Any) -> tuple[float, Optional[datetime]]:
            percent = pct(node)
            resets_at = reset(node)
            # Codex only writes rate-limit updates when Codex is active. If the
            # newest local record says "100%" but its reset time is already in
            # the past, the quota window has renewed and the stale local record
            # must not keep the overlay pinned at 100%.
            if resets_at and resets_at <= now:
                return 0.0, None
            return percent, resets_at

        session_percent, session_reset = window(primary)
        week_percent, week_reset = window(secondary)

        return CodexRateLimits(
            session_percent=session_percent,
            week_percent=week_percent,
            session_reset=session_reset,
            week_reset=week_reset,
            plan_type=str(raw.get("plan_type") or "codex"),
            limit_id=str(raw.get("limit_id") or "codex"),
        )

    def token_usage(self) -> TokenUsage:
        """Aggregate Codex token usage for today / 7 days / 30 days."""
        files = self._session_files()
        if not files:
            return TokenUsage(provider="codex")
        newest_mtime = max(int(p.stat().st_mtime) for p in files)
        cache_key = (len(files), newest_mtime)
        if self._token_cache_key == cache_key and self._token_cache is not None:
            return self._token_cache

        start_today = datetime.now().astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(timezone.utc)
        start_week = _now() - timedelta(days=7)
        start_month = _now() - timedelta(days=30)

        inputs = [0, 0, 0]
        outputs = [0, 0, 0]
        cache = [0, 0, 0]
        totals = [0, 0, 0]
        hourly_raw = [0.0] * 24

        for path in files:
            try:
                if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) < start_month:
                    continue
                with open(path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts = _parse_ts(event.get("timestamp"))
                        if ts is None or ts < start_month:
                            continue
                        payload = event.get("payload")
                        if not isinstance(payload, dict):
                            continue
                        if payload.get("type") != "token_count":
                            continue
                        info = payload.get("info")
                        if not isinstance(info, dict):
                            continue
                        usage = info.get("last_token_usage")
                        if not isinstance(usage, dict):
                            continue
                        inp = int(usage.get("input_tokens") or 0)
                        out = int(usage.get("output_tokens") or 0) + int(
                            usage.get("reasoning_output_tokens") or 0
                        )
                        cached = int(usage.get("cached_input_tokens") or 0)
                        headline = out
                        for idx, since in enumerate((start_today, start_week, start_month)):
                            if ts >= since:
                                inputs[idx] += inp
                                outputs[idx] += out
                                cache[idx] += cached
                                totals[idx] += headline
                        if ts >= start_today:
                            hourly_raw[ts.astimezone().hour] += headline
            except Exception:
                continue

        peak = max(hourly_raw) if any(hourly_raw) else 1.0
        usage = TokenUsage(
            provider="codex",
            totals=tuple(totals),
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            cache=tuple(cache),
            hourly=[round(v / peak, 3) for v in hourly_raw],
        )
        self._token_cache_key = cache_key
        self._token_cache = usage
        return usage
