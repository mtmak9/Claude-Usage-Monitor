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
from .i18n import set_language, tr
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


_SINGLE_INSTANCE_HANDLE = None


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


def _activate_existing_instance() -> None:
    """Best-effort: bring the already running overlay back when launched again."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
        user32.FindWindowW.restype = wintypes.HWND
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        user32.SetForegroundWindow.restype = wintypes.BOOL
        hwnd = user32.FindWindowW(None, constants.APP_NAME)
        if hwnd:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _claim_single_instance() -> bool:
    """Return False when another app instance already owns the Windows mutex."""
    global _SINGLE_INSTANCE_HANDLE
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateMutexW(None, False, constants.SINGLE_INSTANCE_MUTEX_NAME)
        if not handle:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            _activate_existing_instance()
            return False
        _SINGLE_INSTANCE_HANDLE = handle
        return True
    except Exception:
        # If the platform API is unavailable, prefer starting over blocking the app.
        return True


class MonitorApp:
    """Top-level controller owning every long-lived object."""

    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.config = Config()
        # Apply the UI language *before* any widget is built.
        set_language(self.config.language)
        self.db = Database()
        self.history = HistoryService(self.db)
        self.client = AnthropicClient(self.config)
        self.poller = Poller(self.client, self.config)

        self.overlay = Overlay(self.config)
        self.notifications = NotificationManager(self.config)
        self._settings_win: SettingsWindow | None = None
        self._history_win: HistoryWindow | None = None
        self._latest_snapshots: dict[str, UsageSnapshot] = {}
        self._latest_tokens: dict[str, object] = {}

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
        self.poller.tokens_ready.connect(self._on_tokens)
        self.poller.error.connect(lambda e: logging.error("poll error: %s", e))
        self.overlay.request_menu.connect(self._show_context_menu)
        self.overlay.provider_changed.connect(self._on_provider_changed)

        if self.tray is not None:
            self.tray.toggle_overlay.connect(self._toggle_overlay)
            self.tray.toggle_compact.connect(self.overlay.toggle_compact)
            self.tray.refresh_now.connect(lambda: self.poller.poll_now(force=True))
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
    def _on_snapshot(self, provider: str, snap: UsageSnapshot) -> None:
        # Stale snapshots are the last good reading re-shown after a rate-limit
        # (429); display them but don't persist duplicates or re-notify.
        fresh = isinstance(snap, UsageSnapshot) and snap.ok and not snap.is_stale
        active = provider == self.config.provider
        if isinstance(snap, UsageSnapshot):
            self._latest_snapshots[provider] = snap

        # The history database is not provider-aware yet, so only persist the
        # provider currently shown in the detailed panel.
        if fresh and active:
            self.db.insert_snapshot(snap)

        if active:
            self.overlay.update_snapshot(snap)
        else:
            self.overlay.update_provider_status(snap)

        if self.tray is not None and active:
            self.tray.update_state(snap)

        if fresh:
            self.notifications.check_session(snap)
            self.notifications.check_usage(
                snap.week_percent,
                tr("notify_week"),
                key=f"{provider}:week",
            )
        # Token usage (and the hourly activity chart) arrive separately via the
        # poller's tokens_ready signal → overlay.update_tokens.

    def _on_tokens(self, provider: str, tokens: object) -> None:
        self._latest_tokens[provider] = tokens
        if provider == self.config.provider:
            self.overlay.update_tokens(tokens)

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
            self._settings_win.restart_requested.connect(self._restart_app)
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()

    def _apply_settings(self) -> None:
        self.overlay.apply_opacity(self.config.opacity)
        self.overlay.apply_always_on_top(self.config.always_on_top)
        self.overlay.sync_provider_switch(self.config.provider)
        self.overlay.set_compact(self.config.compact, persist=False)
        self.poller.set_interval_seconds(self.config.poll_interval)
        if self.config.provider in self._latest_snapshots:
            self.overlay.update_snapshot(self._latest_snapshots[self.config.provider])
        if self.config.provider in self._latest_tokens:
            self.overlay.update_tokens(self._latest_tokens[self.config.provider])
        self.poller.poll_now(force=True)  # reflect new auth / model immediately

    def _on_provider_changed(self, provider: str) -> None:
        logging.info("provider switched to %s", provider)
        if self._settings_win is not None:
            idx = self._settings_win.provider.findData(provider)
            if idx >= 0:
                self._settings_win.provider.setCurrentIndex(idx)
        if provider in self._latest_snapshots:
            self.overlay.update_snapshot(self._latest_snapshots[provider])
            if self.tray is not None:
                self.tray.update_state(self._latest_snapshots[provider])
        if provider in self._latest_tokens:
            self.overlay.update_tokens(self._latest_tokens[provider])
        self.poller.poll_now(force=True)

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
        box.setWindowTitle(tr("about_title", app=constants.APP_NAME))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<b>{constants.APP_NAME}</b> v{constants.APP_VERSION}<br><br>"
            f"{tr('about_desc1')}<br>"
            f"{tr('about_desc2')}<br><br>"
            f"{tr('about_author')}: <b>{constants.APP_AUTHOR_NAME}</b> "
            f'(<a href="{constants.APP_GITHUB}">{constants.APP_GITHUB}</a>)<br>'
            f"{tr('about_mode')}: <b>{self.client.effective_auth()}</b><br>"
            f"{tr('about_data')}: {constants.DATA_DIR}"
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

    def _restart_app(self) -> None:
        """Relaunch the app (used after a language change) then quit this one."""
        import sys

        from PyQt6.QtCore import QProcess

        try:
            self.config.save()
            if getattr(sys, "frozen", False):
                QProcess.startDetached(sys.executable, sys.argv[1:])
            else:
                QProcess.startDetached(sys.executable, sys.argv)
        except Exception:
            logging.exception("restart failed")
        self._quit()

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
    if not _claim_single_instance():
        logging.info("%s is already running; exiting duplicate instance.", constants.APP_NAME)
        return 0
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
