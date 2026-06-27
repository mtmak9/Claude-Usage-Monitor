"""SQLite persistence for usage snapshots and daily summaries.

The database lives at ``%APPDATA%/ClaudeMonitor/usage.db``.  All access goes
through a single :class:`Database` instance; sqlite3 connections are created per
call (cheap and thread-safe for our low write rate).
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional

from .. import constants
from ..api.models import UsageSnapshot

log = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    requests_remaining INTEGER,
    tokens_remaining  INTEGER,
    session_util      REAL,
    week_util         REAL,
    model             TEXT,
    is_peak           INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON usage_snapshots(timestamp);

CREATE TABLE IF NOT EXISTS daily_summaries (
    date              TEXT PRIMARY KEY,
    total_prompts     INTEGER DEFAULT 0,
    peak_session_util REAL DEFAULT 0,
    peak_week_util    REAL DEFAULT 0
);
"""


class Database:
    def __init__(self, path=None) -> None:
        self.path = str(path or constants.DATABASE_PATH)
        constants.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        try:
            with self._conn() as conn:
                conn.executescript(_SCHEMA)
        except Exception as exc:  # pragma: no cover
            log.error("Could not initialise database: %s", exc)

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def insert_snapshot(self, snap: UsageSnapshot) -> None:
        if not snap.ok:
            return  # don't persist error snapshots
        try:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO usage_snapshots
                       (timestamp, requests_remaining, tokens_remaining,
                        session_util, week_util, model, is_peak)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        snap.timestamp.astimezone(timezone.utc).isoformat(),
                        snap.requests_remaining,
                        snap.tokens_remaining,
                        snap.session_percent,
                        snap.week_percent,
                        snap.model,
                        1 if snap.is_peak else 0,
                    ),
                )
            self._touch_daily(snap)
        except Exception as exc:  # pragma: no cover
            log.error("insert_snapshot failed: %s", exc)

    def _touch_daily(self, snap: UsageSnapshot) -> None:
        date = snap.timestamp.astimezone().strftime("%Y-%m-%d")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT total_prompts, peak_session_util, peak_week_util "
                "FROM daily_summaries WHERE date = ?",
                (date,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO daily_summaries "
                    "(date, total_prompts, peak_session_util, peak_week_util) "
                    "VALUES (?, 0, ?, ?)",
                    (date, snap.session_percent, snap.week_percent),
                )
            else:
                conn.execute(
                    "UPDATE daily_summaries SET "
                    "peak_session_util = MAX(peak_session_util, ?), "
                    "peak_week_util = MAX(peak_week_util, ?) "
                    "WHERE date = ?",
                    (snap.session_percent, snap.week_percent, date),
                )

    def bump_prompt_count(self, when: Optional[datetime] = None, count: int = 1) -> None:
        when = when or datetime.now(timezone.utc)
        date = when.astimezone().strftime("%Y-%m-%d")
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO daily_summaries (date, total_prompts) VALUES (?, ?) "
                    "ON CONFLICT(date) DO UPDATE SET total_prompts = total_prompts + ?",
                    (date, count, count),
                )
        except Exception as exc:  # pragma: no cover
            log.error("bump_prompt_count failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def snapshots_since(self, iso_timestamp: str) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM usage_snapshots WHERE timestamp >= ? ORDER BY timestamp",
                (iso_timestamp,),
            ).fetchall()

    def recent_snapshots(self, limit: int = 500) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM usage_snapshots ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def daily_summaries(self, limit: int = 30) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM daily_summaries ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def prompt_count_for_date(self, date: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT total_prompts FROM daily_summaries WHERE date = ?", (date,)
            ).fetchone()
            return int(row["total_prompts"]) if row else 0

    def purge_older_than(self, iso_timestamp: str) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    "DELETE FROM usage_snapshots WHERE timestamp < ?", (iso_timestamp,)
                )
        except Exception as exc:  # pragma: no cover
            log.error("purge failed: %s", exc)
