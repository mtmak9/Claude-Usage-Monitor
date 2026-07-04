"""User notifications with threshold de-duplication.

Uses the Qt system-tray balloon when available and falls back to the native
Windows toast (``win10toast``).  The :class:`NotificationManager` makes sure we
don't spam the user with the same threshold repeatedly within a usage window.
"""
from __future__ import annotations

import logging
from datetime import datetime
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
        # Highest threshold already announced for the current window, keyed by
        # provider/window so Claude, Codex, session and week never block each other.
        self._last_levels: dict[str, float] = {}
        self._session_state: dict[str, dict] = {}

    def set_tray(self, tray) -> None:
        self.tray = tray

    # ------------------------------------------------------------------ #
    def _emit(self, title: str, message: str, *, sound: str | bool = False) -> None:
        log.info("NOTIFY: %s - %s", title, message)
        if self.tray is not None:
            try:
                from PyQt6.QtWidgets import QSystemTrayIcon

                if not QSystemTrayIcon.supportsMessages():
                    raise RuntimeError("system tray messages are not supported")
                self.tray.show_message(title, message)
                if sound:
                    self._play_sound(sound)
                return
            except Exception as exc:  # pragma: no cover
                log.debug("tray message failed: %s", exc)
        if _native_toast(title, message):
            if sound:
                self._play_sound(sound)
            return
        if sound:
            self._play_sound(sound)
        log.info("NOTIFY: %s — %s", title, message)

    @staticmethod
    def _sound_path(kind: str | bool):
        if kind == "limit_hit":
            return constants.LIMIT_HIT_SOUND_PATH
        return constants.SESSION_RENEWED_SOUND_PATH

    @classmethod
    def _play_sound(cls, kind: str | bool = "renewed") -> None:
        try:
            import winsound

            sound_path = cls._sound_path(kind)
            if sound_path.exists():
                winsound.PlaySound(
                    str(sound_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                return
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication

            QApplication.beep()
        except Exception:
            pass

    @staticmethod
    def _ai_key(snap) -> str:
        return "codex" if getattr(snap, "model", "") == "codex" else "claude"

    @staticmethod
    def _ai_label(snap) -> str:
        if getattr(snap, "model", "") == "codex":
            return "Codex"
        return "Claude"

    # ------------------------------------------------------------------ #
    def check_usage(self, percent: float, window_label: str = "Limit", *, key: str | None = None) -> None:
        """Evaluate a utilisation value and notify on threshold crossings."""
        if not self.config.notifications_enabled:
            return

        key = key or window_label
        last_level = self._last_levels.get(key, 0.0)

        # Reset the latch once usage falls back to a low level (new window).
        if percent < constants.NOTIFY_THRESHOLDS[0] - 5:
            self._last_levels[key] = 0.0
            return

        crossed = 0.0
        for threshold in constants.NOTIFY_THRESHOLDS:
            cfg_key = {80.0: "threshold_80", 90.0: "threshold_90", 100.0: "threshold_100"}[
                threshold
            ]
            if not self.config.get(f"notifications.{cfg_key}", True):
                continue
            if percent >= threshold > last_level:
                crossed = threshold

        if crossed:
            self._last_levels[key] = crossed
            emoji = "🔴" if crossed >= 100 else ("🟠" if crossed >= 90 else "🟡")
            self._emit(
                f"{emoji} Claude Usage Monitor",
                tr("notify_body", label=window_label, pct=int(round(percent)), th=int(crossed)),
            )

    def check_session(self, snap) -> None:
        """Notify for the active AI's 5h session thresholds and renewal."""
        if not self.config.notifications_enabled or snap is None or not getattr(snap, "ok", False):
            return

        ai_key = self._ai_key(snap)
        ai = self._ai_label(snap)
        key = f"{ai_key}:session"
        state = self._session_state.setdefault(
            key,
            {"last_level": 0.0, "was_full": False, "reset": None},
        )
        percent = float(getattr(snap, "session_percent", 0.0) or 0.0)
        reset = getattr(snap, "session_reset", None)
        previous_reset = state.get("reset")

        reset_moved_forward = (
            isinstance(reset, datetime)
            and isinstance(previous_reset, datetime)
            and reset > previous_reset
        )
        # A reset timestamp can move forward while the account is still reported
        # at 100%. That is not a usable renewed session; do not play the renewal
        # chime until utilisation actually drops below full.
        renewed = bool(
            state.get("was_full")
            and (
                percent < 90.0
                or (reset_moved_forward and percent < 100.0)
            )
        )
        if renewed:
            self._emit(
                "🔔 Claude Usage Monitor",
                tr("notify_session_renewed", ai=ai, pct=int(round(percent))),
                sound="renewed",
            )
            state["was_full"] = False
            state["last_level"] = 0.0
            renewed = True

        crossed = 0.0
        if not renewed:
            for threshold in (90.0, 100.0):
                cfg_key = "threshold_90" if threshold == 90.0 else "threshold_100"
                if not self.config.get(f"notifications.{cfg_key}", True):
                    continue
                if percent >= threshold > float(state.get("last_level", 0.0)):
                    crossed = threshold

            if crossed:
                state["last_level"] = crossed
                if crossed >= 100:
                    self._emit(
                        "🔴 Claude Usage Monitor",
                        tr("notify_session_full", ai=ai),
                        sound="limit_hit",
                    )
                else:
                    self._emit(
                        "🟠 Claude Usage Monitor",
                        tr("notify_session_90", ai=ai, pct=int(round(percent))),
                    )

        if percent >= 100.0:
            state["was_full"] = True
        if percent < 80.0 and not state.get("was_full"):
            state["last_level"] = 0.0
        state["reset"] = reset

    def notify(self, title: str, message: str) -> None:
        """Send an ad-hoc notification (ignores thresholds)."""
        self._emit(title, message)
