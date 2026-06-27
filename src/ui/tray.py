"""System tray icon: colour-coded status, tooltip, and right-click menu.

Icons are drawn at runtime with :class:`QPainter` (no image files needed) — a
filled circle whose colour reflects the worst current utilisation, with a subtle
ring so it reads well on both light and dark taskbars.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .. import constants
from ..api.models import UsageSnapshot
from .styles.colors import Colors


def make_circle_icon(color: str, size: int = 64) -> QIcon:
    """Return a QIcon containing a filled circle of the given colour."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = size * 0.12
    # Outer subtle ring
    ring = QColor(Colors.BG_PRIMARY)
    ring.setAlpha(180)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ring)
    painter.drawEllipse(int(margin / 2), int(margin / 2), int(size - margin), int(size - margin))

    # Filled status disc
    painter.setBrush(QColor(color))
    painter.drawEllipse(int(margin), int(margin), int(size - 2 * margin), int(size - 2 * margin))

    # Small inner highlight
    hi = QColor(255, 255, 255, 60)
    painter.setBrush(hi)
    painter.drawEllipse(int(size * 0.30), int(size * 0.24), int(size * 0.22), int(size * 0.16))

    painter.end()
    return QIcon(pix)


class Tray(QObject):
    toggle_overlay = pyqtSignal()
    toggle_compact = pyqtSignal()
    refresh_now = pyqtSignal()
    open_history = pyqtSignal()
    open_settings = pyqtSignal()
    open_about = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, app) -> None:
        super().__init__()
        self._icons = {
            "gray": make_circle_icon(Colors.TEXT_MUTED),
            "green": make_circle_icon(Colors.GREEN),
            "yellow": make_circle_icon(Colors.YELLOW),
            "orange": make_circle_icon(Colors.ORANGE),
            "red": make_circle_icon(Colors.RED),
        }
        self._tray = QSystemTrayIcon(self._icons["gray"], app)
        self._tray.setToolTip(f"{constants.APP_NAME}: łączenie…")
        self._menu = self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

    # ------------------------------------------------------------------ #
    def _build_menu(self) -> QMenu:
        menu = QMenu()

        self._act_show = QAction("Pokaż / ukryj widżet", menu)
        self._act_show.triggered.connect(self.toggle_overlay.emit)
        menu.addAction(self._act_show)

        self._act_compact = QAction("Tryb kompaktowy / pełny", menu)
        self._act_compact.triggered.connect(self.toggle_compact.emit)
        menu.addAction(self._act_compact)

        menu.addSeparator()

        act_refresh = QAction("Odśwież teraz", menu)
        act_refresh.triggered.connect(self.refresh_now.emit)
        menu.addAction(act_refresh)

        act_history = QAction("Historia użycia…", menu)
        act_history.triggered.connect(self.open_history.emit)
        menu.addAction(act_history)

        act_settings = QAction("Ustawienia…", menu)
        act_settings.triggered.connect(self.open_settings.emit)
        menu.addAction(act_settings)

        menu.addSeparator()

        act_about = QAction("O programie", menu)
        act_about.triggered.connect(self.open_about.emit)
        menu.addAction(act_about)

        act_quit = QAction("Zakończ", menu)
        act_quit.triggered.connect(self.quit_app.emit)
        menu.addAction(act_quit)
        return menu

    def context_menu(self) -> QMenu:
        return self._menu

    # ------------------------------------------------------------------ #
    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_overlay.emit()

    # ------------------------------------------------------------------ #
    def _bucket(self, percent: float) -> str:
        if percent >= 90:
            return "red"
        if percent >= 80:
            return "orange"
        if percent >= 50:
            return "yellow"
        return "green"

    def update_state(self, snap: Optional[UsageSnapshot]) -> None:
        if snap is None or not snap.ok:
            self._tray.setIcon(self._icons["gray"])
            msg = snap.error if (snap and snap.error) else "łączenie…"
            self._tray.setToolTip(f"{constants.APP_NAME}: {msg}")
            return
        bucket = self._bucket(snap.worst_percent)
        self._tray.setIcon(self._icons[bucket])
        self._tray.setToolTip(
            f"{constants.APP_NAME}\n"
            f"Sesja {snap.session_percent:.0f}%  |  "
            f"Tydzień {snap.week_percent:.0f}%"
        )

    def show_message(self, title: str, message: str) -> None:
        self._tray.showMessage(
            title, message, QSystemTrayIcon.MessageIcon.Information, 6000
        )
