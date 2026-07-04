"""Read real token usage from local Claude Code session logs.

Claude Code writes one JSONL file per session under ``~/.claude/projects/**`` and
every assistant record carries a ``message.usage`` block::

    {"input_tokens": 16570, "cache_creation_input_tokens": 3245,
     "cache_read_input_tokens": 24988, "output_tokens": 346, ...}

We sum those per local day to drive the overlay's TOKENS card (today / 7d / 30d
plus an input·output·cache breakdown) and the hourly activity chart.

NOTE: this reflects **Claude Code** (CLI / agent) usage only — claude.ai web/desktop
chat is not logged locally, so it is not counted here.

Per-file results are cached by mtime, and files older than the 30-day window are
skipped, so after the first pass only the active session file is re-read.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token totals for today / last 7 days / last 30 days (index 0/1/2)."""

    provider: str = "claude"
    totals: tuple = (0, 0, 0)
    inputs: tuple = (0, 0, 0)
    outputs: tuple = (0, 0, 0)
    cache: tuple = (0, 0, 0)
    hourly: list = field(default_factory=lambda: [0.0] * 24)  # today, normalised 0-1

    def headline_for_tab(self, idx: int) -> int:
        """The 'tokens used' figure shown big: input + output (excludes cache
        reads, which would otherwise dominate and mislead)."""
        i = idx if 0 <= idx < 3 else 0
        if self.provider == "codex":
            # Codex sends a large working context on every model turn. Showing
            # input + output as the headline makes the counter look wildly
            # inflated, so Codex uses generated tokens as the headline.
            return self.outputs[i]
        return self.inputs[i] + self.outputs[i]

    def breakdown_for_tab(self, idx: int) -> tuple:
        i = idx if 0 <= idx < 3 else 0
        return self.inputs[i], self.outputs[i], self.cache[i]


class TokenUsageReader:
    """Aggregates token usage across the local Claude Code session logs."""

    def __init__(self) -> None:
        self._dir = Path.home() / ".claude" / "projects"
        # path -> (mtime, {date_str: [input, output, cache]})
        self._cache: dict[str, tuple[float, dict]] = {}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _local_date(ts: str | None):
        if not ts:
            return None, None
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone()
            return dt.strftime("%Y-%m-%d"), dt.hour
        except Exception:
            return None, None

    def _parse_file(self, path: Path) -> dict:
        """Return ``{date_str: [input, output, cache]}`` for one session file."""
        agg: dict[str, list] = {}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    msg = rec.get("message")
                    usage = msg.get("usage") if isinstance(msg, dict) else rec.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    date, _hour = self._local_date(rec.get("timestamp"))
                    if not date:
                        continue
                    inp = int(usage.get("input_tokens") or 0)
                    out = int(usage.get("output_tokens") or 0)
                    cache = int(usage.get("cache_creation_input_tokens") or 0) + int(
                        usage.get("cache_read_input_tokens") or 0
                    )
                    bucket = agg.setdefault(date, [0, 0, 0])
                    bucket[0] += inp
                    bucket[1] += out
                    bucket[2] += cache
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("token log parse failed for %s: %s", path, exc)
        return agg

    def _today_hourly(self, today: str) -> list:
        """Total tokens per hour for *today* (normalised 0-1), from today's files."""
        hourly = [0.0] * 24
        cutoff = datetime.now().timestamp() - 36 * 3600  # only files touched ~today
        try:
            files = [p for p in self._dir.rglob("*.jsonl") if p.stat().st_mtime >= cutoff]
        except Exception:
            files = []
        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if '"usage"' not in line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        msg = rec.get("message")
                        usage = msg.get("usage") if isinstance(msg, dict) else rec.get("usage")
                        if not isinstance(usage, dict):
                            continue
                        date, hour = self._local_date(rec.get("timestamp"))
                        if date != today or hour is None:
                            continue
                        hourly[hour] += int(usage.get("input_tokens") or 0) + int(
                            usage.get("output_tokens") or 0
                        )
            except Exception:
                continue
        peak = max(hourly) if any(hourly) else 1.0
        return [round(v / peak, 3) for v in hourly]

    # ------------------------------------------------------------------ #
    def read(self) -> TokenUsage:
        if not self._dir.exists():
            return TokenUsage(provider="claude")

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        week = {(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
        month = {(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)}
        cutoff = now.timestamp() - 31 * 86400  # files older than the window can't count

        try:
            files = list(self._dir.rglob("*.jsonl"))
        except Exception:
            files = []

        combined: dict[str, list] = {}
        seen: set[str] = set()
        for path in files:
            try:
                mtime = path.stat().st_mtime
            except Exception:
                continue
            if mtime < cutoff:
                continue
            key = str(path)
            seen.add(key)
            cached = self._cache.get(key)
            if cached and cached[0] == mtime:
                agg = cached[1]
            else:
                agg = self._parse_file(path)
                self._cache[key] = (mtime, agg)
            for date, vals in agg.items():
                c = combined.setdefault(date, [0, 0, 0])
                c[0] += vals[0]
                c[1] += vals[1]
                c[2] += vals[2]

        # Forget files that no longer exist / aged out of the window.
        for k in list(self._cache.keys()):
            if k not in seen:
                del self._cache[k]

        def window(dates) -> tuple:
            inp = out = ca = 0
            for date in dates:
                v = combined.get(date)
                if v:
                    inp += v[0]
                    out += v[1]
                    ca += v[2]
            return inp, out, ca

        ti, to, tc = window({today})
        wi, wo, wc = window(week)
        mi, mo, mc = window(month)
        return TokenUsage(
            provider="claude",
            totals=(ti + to + tc, wi + wo + wc, mi + mo + mc),
            inputs=(ti, wi, mi),
            outputs=(to, wo, mo),
            cache=(tc, wc, mc),
            hourly=self._today_hourly(today),
        )
