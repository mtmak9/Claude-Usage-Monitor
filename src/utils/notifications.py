"""User notifications with threshold de-duplication.

Tries the native Windows toast (``win10toast``) first and falls back to the
Qt system-tray balloon message.  The :class:`NotificationManager` makes sure we
don't spam the user with the same threshold repeatedly within a usage window.
"""
from __future__ import annotations

import logging
from typing import Optional

from .. import constants
from ..i18n import tr

log = logging.getLogger(__name__)

try:
    from win10toast import ToastNotifier  # type: ignore

    _toaster: Optional["ToastNotifier"] = ToastNotifier()
except Exception:  # pragma: no cover - optional dependency / non-Windows
    _toaster = None


def _native_toast(title: str, message: str) -> bool:
    if _toaster is None:
        return False
    try:
        # threaded=True so it never blocks the Qt event loop
        _toaster.show_toast(title, message, duration=6, threaded=True)
        return True
    except Exception as exc:  # pragma: no cover
        log.debug("win10toast failed: %s", exc)
        return False


class NotificationManager:
    """Decides *when* to notify and routes the message to an available sink."""

    def __init__(self, config, tray=None) -> None:
        self.config = config
        self.tray = tray
        # Highest threshold already announced for the current window.
        self._last_level: float = 0.0

    def set_tray(self, tray) -> None:
        self.tray = tray

    # ------------------------------------------------------------------ #
    def _emit(self, title: str, message: str) -> None:
        if _native_toast(title, message):
            return
        if self.tray is not None:
            try:
                self.tray.show_message(title, message)
                return
            except Exception as exc:  # pragma: no cover
                log.debug("tray message failed: %s", exc)
        log.info("NOTIFY: %s — %s", title, message)

    # ------------------------------------------------------------------ #
    def check_usage(self, percent: float, window_label: str = "Limit") -> None:
        """Evaluate a utilisation value and notify on threshold crossings."""
        if not self.config.notifications_enabled:
            return

        # Reset the latch once usage falls back to a low level (new window).
        if percent < constants.NOTIFY_THRESHOLDS[0] - 5:
            self._last_level = 0.0
            return

        crossed = 0.0
        for threshold in constants.NOTIFY_THRESHOLDS:
            key = {80.0: "threshold_80", 90.0: "threshold_90", 100.0: "threshold_100"}[
                threshold
            ]
            if not self.config.get(f"notifications.{key}", True):
                continue
            if percent >= threshold > self._last_level:
                crossed = threshold

        if crossed:
            self._last_level = crossed
            emoji = "🔴" if crossed >= 100 else ("🟠" if crossed >= 90 else "🟡")
            self._emit(
                f"{emoji} Claude Usage Monitor",
                tr("notify_body", label=window_label, pct=int(round(percent)), th=int(crossed)),
            )

    def notify(self, title: str, message: str) -> None:
        """Send an ad-hoc notification (ignores thresholds)."""
        self._emit(title, message)
