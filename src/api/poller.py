"""Periodic, non-blocking usage polling built on Qt.

A :class:`QTimer` fires on the configured interval; each tick dispatches the
(blocking) network call to a worker thread via :class:`QThreadPool`, then emits
``snapshot_ready`` / ``activity_ready`` back on the GUI thread.  This keeps the
overlay perfectly responsive even on slow networks.
"""
from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from .. import constants
from .models import ActivityData, UsageSnapshot

log = logging.getLogger(__name__)


class _WorkerSignals(QObject):
    snapshot = pyqtSignal(str, object)   # provider, UsageSnapshot
    activity = pyqtSignal(object)   # ActivityData
    tokens = pyqtSignal(str, object)     # provider, TokenUsage
    failed = pyqtSignal(str, str)         # provider, error


class _FetchWorker(QRunnable):
    def __init__(self, client, provider: str, want_activity: bool) -> None:
        super().__init__()
        self.client = client
        self.provider = provider
        self.want_activity = want_activity
        self.signals = _WorkerSignals()

    def run(self) -> None:  # executed on a pool thread
        try:
            snap = self.client.fetch_snapshot(self.provider)
            self.signals.snapshot.emit(self.provider, snap)
            if self.want_activity:
                try:
                    self.signals.activity.emit(self.client.activity())
                except Exception:  # activity is best-effort
                    pass
                try:
                    # Parsing the local token logs can take a moment — fine here,
                    # we're on a pool thread, not the GUI thread.
                    self.signals.tokens.emit(self.provider, self.client.token_usage(self.provider))
                except Exception:  # tokens are best-effort
                    pass
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("poll worker crashed")
            self.signals.failed.emit(self.provider, str(exc))


class Poller(QObject):
    """Owns the timer and emits results for the rest of the app to consume."""

    snapshot_ready = pyqtSignal(str, object)   # provider, UsageSnapshot
    activity_ready = pyqtSignal(object)   # ActivityData
    tokens_ready = pyqtSignal(str, object)     # provider, TokenUsage
    error = pyqtSignal(str)
    PROVIDERS = ("claude", "codex")

    def __init__(self, client, config) -> None:
        super().__init__()
        self.client = client
        self.config = config
        self._pool = QThreadPool.globalInstance()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll_now)
        self._last_worst_by_provider: dict[str, float] = {}
        self._last_started: dict[str, float] = {}
        self._in_flight: set[str] = set()

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self._apply_interval()
        self._timer.start()
        # Kick off an immediate first read so the UI isn't empty.
        QTimer.singleShot(150, lambda: self.poll_now(force=True))

    def stop(self) -> None:
        self._timer.stop()

    def _apply_interval(self) -> None:
        interval = self.config.poll_interval
        worst = max(self._last_worst_by_provider.values(), default=0.0)
        if self.config.smart_polling and worst >= constants.THRESHOLD_WARN:
            interval = min(interval, constants.SMART_POLL_FAST)
        elif self.config.smart_polling and worst < constants.THRESHOLD_OK:
            interval = max(interval, min(constants.SMART_POLL_SLOW, interval * 2))
        self._timer.setInterval(max(constants.MIN_POLL_INTERVAL, interval) * 1000)

    def _floor_for_provider(self, provider: str) -> int:
        """Provider-specific floor. Claude OAuth is stricter than local Codex."""
        floor = constants.MIN_POLL_INTERVAL
        try:
            if provider == "claude" and self.client.effective_auth_for_provider("claude") == "oauth":
                floor = max(floor, constants.MIN_OAUTH_POLL_INTERVAL)
        except Exception:
            pass
        return floor

    def set_interval_seconds(self, seconds: int) -> None:
        self._timer.setInterval(max(constants.MIN_POLL_INTERVAL, seconds) * 1000)

    # ------------------------------------------------------------------ #
    def poll_now(self, force: bool = False) -> None:
        """Poll every provider.

        The overlay still shows one detailed provider at a time, but both status
        pills need fresh data.  Each provider keeps its own cooldown so the
        Claude OAuth endpoint is not called faster than its rate limit while
        Codex can still refresh from local logs more often.
        """
        for provider in self.PROVIDERS:
            self._poll_provider(provider, force=bool(force))
        self._apply_interval()

    def _poll_provider(self, provider: str, *, force: bool = False) -> None:
        if provider in self._in_flight:
            return

        now = time.monotonic()
        last = self._last_started.get(provider, 0.0)
        if not force and (now - last) < self._floor_for_provider(provider):
            return

        self._last_started[provider] = now
        self._in_flight.add(provider)
        worker = _FetchWorker(self.client, provider=provider, want_activity=True)
        worker.signals.snapshot.connect(self._on_snapshot)
        worker.signals.activity.connect(self.activity_ready.emit)
        worker.signals.tokens.connect(self._on_tokens)
        worker.signals.failed.connect(self._on_failed)
        self._pool.start(worker)

    def _on_snapshot(self, provider: str, snap: UsageSnapshot) -> None:
        self._in_flight.discard(provider)
        if isinstance(snap, UsageSnapshot):
            self._last_worst_by_provider[provider] = snap.worst_percent
            self._apply_interval()  # smart-polling may change cadence
        self.snapshot_ready.emit(provider, snap)

    def _on_tokens(self, provider: str, tokens) -> None:
        self.tokens_ready.emit(provider, tokens)

    def _on_failed(self, provider: str, error: str) -> None:
        self._in_flight.discard(provider)
        self.error.emit(error)
