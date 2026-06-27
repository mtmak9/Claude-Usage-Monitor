"""Periodic, non-blocking usage polling built on Qt.

A :class:`QTimer` fires on the configured interval; each tick dispatches the
(blocking) network call to a worker thread via :class:`QThreadPool`, then emits
``snapshot_ready`` / ``activity_ready`` back on the GUI thread.  This keeps the
overlay perfectly responsive even on slow networks.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from .. import constants
from .models import ActivityData, UsageSnapshot

log = logging.getLogger(__name__)


class _WorkerSignals(QObject):
    snapshot = pyqtSignal(object)   # UsageSnapshot
    activity = pyqtSignal(object)   # ActivityData
    failed = pyqtSignal(str)


class _FetchWorker(QRunnable):
    def __init__(self, client, want_activity: bool) -> None:
        super().__init__()
        self.client = client
        self.want_activity = want_activity
        self.signals = _WorkerSignals()

    def run(self) -> None:  # executed on a pool thread
        try:
            snap = self.client.fetch_snapshot()
            self.signals.snapshot.emit(snap)
            if self.want_activity:
                try:
                    self.signals.activity.emit(self.client.activity())
                except Exception:  # activity is best-effort
                    pass
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("poll worker crashed")
            self.signals.failed.emit(str(exc))


class Poller(QObject):
    """Owns the timer and emits results for the rest of the app to consume."""

    snapshot_ready = pyqtSignal(object)   # UsageSnapshot
    activity_ready = pyqtSignal(object)   # ActivityData
    error = pyqtSignal(str)

    def __init__(self, client, config) -> None:
        super().__init__()
        self.client = client
        self.config = config
        self._pool = QThreadPool.globalInstance()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll_now)
        self._last_worst = 0.0

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self._apply_interval()
        self._timer.start()
        # Kick off an immediate first read so the UI isn't empty.
        QTimer.singleShot(150, self.poll_now)

    def stop(self) -> None:
        self._timer.stop()

    def _apply_interval(self) -> None:
        interval = self.config.poll_interval
        if self.config.smart_polling and self._last_worst >= constants.THRESHOLD_WARN:
            interval = min(interval, constants.SMART_POLL_FAST)
        elif self.config.smart_polling and self._last_worst < constants.THRESHOLD_OK:
            interval = max(interval, min(constants.SMART_POLL_SLOW, interval * 2))
        self._timer.setInterval(max(self._floor(), interval) * 1000)

    def _floor(self) -> int:
        """Lowest interval we'll poll at, raised in OAuth mode to respect the
        usage endpoint's rate limit."""
        floor = constants.MIN_POLL_INTERVAL
        try:
            if self.client.effective_auth() == "oauth":
                floor = max(floor, constants.MIN_OAUTH_POLL_INTERVAL)
        except Exception:
            pass
        return floor

    def set_interval_seconds(self, seconds: int) -> None:
        self._timer.setInterval(max(self._floor(), seconds) * 1000)

    # ------------------------------------------------------------------ #
    def poll_now(self) -> None:
        worker = _FetchWorker(self.client, want_activity=True)
        worker.signals.snapshot.connect(self._on_snapshot)
        worker.signals.activity.connect(self.activity_ready.emit)
        worker.signals.failed.connect(self.error.emit)
        self._pool.start(worker)

    def _on_snapshot(self, snap: UsageSnapshot) -> None:
        if isinstance(snap, UsageSnapshot):
            self._last_worst = snap.worst_percent
            self._apply_interval()  # smart-polling may change cadence
        self.snapshot_ready.emit(snap)
