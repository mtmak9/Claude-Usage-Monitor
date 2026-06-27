"""Application entry point — wires the API, storage and UI layers together.

Run with either:

    python -m src.main          (from the project root)
    python src/main.py          (the bootstrap below makes this work too)
"""
from __future__ import annotations

# --- allow running this file directly (sets up the package context) -------- #
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "src"

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from . import constants
from .api.client import AnthropicClient
from .api.models import UsageSnapshot
from .api.poller import Poller
from .config import Config
from .storage.database import Database
from .storage.history import HistoryService
from .ui.overlay import Overlay
from .ui.settings_window import SettingsWindow
from .ui.history_window import HistoryWindow
from .ui.styles.dark_theme import build_stylesheet
from .ui.tray import Tray
from .utils.notifications import NotificationManager


def _setup_logging() -> None:
    constants.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(constants.LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _set_app_user_model_id() -> None:
    """Give Windows a stable AppUserModelID (taskbar grouping + toasts)."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"{constants.APP_AUTHOR}.{constants.APP_ID}.{constants.APP_VERSION}"
        )
    except Exception:
        pass


class MonitorApp:
    """Top-level controller owning every long-lived object."""

    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.config = Config()
        self.db = Database()
        self.history = HistoryService(self.db)
        self.client = AnthropicClient(self.config)
        self.poller = Poller(self.client, self.config)

        self.overlay = Overlay(self.config)
        self.notifications = NotificationManager(self.config)
        self._settings_win: SettingsWindow | None = None
        self._history_win: HistoryWindow | None = None

        tray_available = self._init_tray()
        self._connect()
        self._start_clock()

        self.overlay.show()
        if tray_available:
            self.tray.show()
        self.poller.start()

    # ------------------------------------------------------------------ #
    def _init_tray(self) -> bool:
        from PyQt6.QtWidgets import QSystemTrayIcon

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logging.warning("System tray unavailable — running overlay only.")
            self.tray = None
            return False
        self.tray = Tray(self.qt_app)
        self.notifications.set_tray(self.tray)
        return True

    def _connect(self) -> None:
        self.poller.snapshot_ready.connect(self._on_snapshot)
        self.poller.error.connect(lambda e: logging.error("poll error: %s", e))
        self.overlay.request_menu.connect(self._show_context_menu)

        if self.tray is not None:
            self.tray.toggle_overlay.connect(self._toggle_overlay)
            self.tray.toggle_compact.connect(self.overlay.toggle_compact)
            self.tray.refresh_now.connect(self.poller.poll_now)
            self.tray.open_history.connect(self._open_history)
            self.tray.open_settings.connect(self._open_settings)
            self.tray.open_about.connect(self._open_about)
            self.tray.quit_app.connect(self._quit)

    def _start_clock(self) -> None:
        # 1 Hz timer keeps countdowns / peak marker fresh between polls.
        self._clock = QTimer(self.qt_app)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self.overlay.refresh_dynamic)
        self._clock.start()

    # ------------------------------------------------------------------ #
    # Data flow
    # ------------------------------------------------------------------ #
    def _on_snapshot(self, snap: UsageSnapshot) -> None:
        # Stale snapshots are the last good reading re-shown after a rate-limit
        # (429); display them but don't persist duplicates or re-notify.
        fresh = isinstance(snap, UsageSnapshot) and snap.ok and not snap.is_stale
        if fresh:
            self.db.insert_snapshot(snap)

        self.overlay.update_snapshot(snap)
        if self.tray is not None:
            self.tray.update_state(snap)

        if fresh:
            self.notifications.check_usage(snap.session_percent, "Sesja 5h")
            self.notifications.check_usage(snap.week_percent, "Tydzień 7d")

        # Refresh the prompt/activity sections from the right source.
        try:
            if self.client.effective_auth() == "mock":
                activity = self.client.activity()
            else:
                activity = self.history.compute_activity()
            self.overlay.update_activity(activity)
        except Exception:  # activity is best-effort
            logging.debug("activity refresh failed", exc_info=True)

    # ------------------------------------------------------------------ #
    # UI actions
    # ------------------------------------------------------------------ #
    def _toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()
            self.overlay.raise_()
            self.overlay.activateWindow()

    def _show_context_menu(self, point) -> None:
        if self.tray is not None:
            self.tray.context_menu().exec(point)

    def _open_settings(self) -> None:
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self.config, self.client)
            self._settings_win.applied.connect(self._apply_settings)
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()

    def _apply_settings(self) -> None:
        self.overlay.apply_opacity(self.config.opacity)
        self.overlay.apply_always_on_top(self.config.always_on_top)
        self.overlay.set_compact(self.config.compact, persist=False)
        self.poller.set_interval_seconds(self.config.poll_interval)
        self.poller.poll_now()  # reflect new auth / model immediately

    def _open_history(self) -> None:
        if self._history_win is None:
            self._history_win = HistoryWindow(self.history)
        else:
            self._history_win.reload()
        self._history_win.show()
        self._history_win.raise_()
        self._history_win.activateWindow()

    def _open_about(self) -> None:
        box = QMessageBox(self.overlay)
        box.setWindowTitle(f"O programie — {constants.APP_NAME}")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<b>{constants.APP_NAME}</b> v{constants.APP_VERSION}<br><br>"
            "Monitor limitów użycia Claude w czasie rzeczywistym.<br>"
            "Widżet zawsze na wierzchu + ikona w zasobniku.<br><br>"
            f"Autor: <b>{constants.APP_AUTHOR_NAME}</b> "
            f'(<a href="{constants.APP_GITHUB}">{constants.APP_GITHUB}</a>)<br>'
            f"Tryb: <b>{self.client.effective_auth()}</b><br>"
            f"Folder danych: {constants.DATA_DIR}"
        )
        # Show the app icon and make the GitHub link clickable (opens in browser).
        icon_path = constants.ASSETS_DIR / "app.png"
        if icon_path.exists():
            box.setIconPixmap(
                QPixmap(str(icon_path)).scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        for label in box.findChildren(QLabel):
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.exec()

    def _quit(self) -> None:
        try:
            self.poller.stop()
            self.config.save()
        finally:
            if self.tray is not None:
                self.tray.hide()
            self.qt_app.quit()


def main() -> int:
    _setup_logging()
    _set_app_user_model_id()

    app = QApplication([])
    app.setApplicationName(constants.APP_NAME)
    app.setApplicationDisplayName(constants.APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # live in the tray
    app.setStyleSheet(build_stylesheet())

    # Window / taskbar icon (the built .exe also embeds it via --icon).
    _icon = constants.ASSETS_DIR / "app.png"
    if _icon.exists():
        app.setWindowIcon(QIcon(str(_icon)))

    QGuiApplication.setDesktopSettingsAware(True)

    controller = MonitorApp(app)
    _ = controller  # keep a reference alive
    logging.info("%s v%s started", constants.APP_NAME, constants.APP_VERSION)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
