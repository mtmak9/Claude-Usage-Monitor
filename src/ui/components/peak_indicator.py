"""24-hour peak / off-peak strip with a live "now" marker.

Green segments are off-peak, orange segments are peak (US Pacific business
hours).  A vertical marker shows the current Pacific time position.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from ...utils import peak_hours
from ..styles.colors import Colors


class PeakIndicator(QWidget):
    def __init__(self, parent=None, height: int = 14) -> None:
        super().__init__(parent)
        self._bar_height = height
        self._now_fraction = 0.0
        self._segments = peak_hours.peak_segments()
        self.setMinimumHeight(height + 14)
        self.setMaximumHeight(height + 14)

    def refresh(self) -> None:
        self._now_fraction = peak_hours.current_pacific_hour_fraction()
        self._segments = peak_hours.peak_segments()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self._bar_height
        radius = h / 2.0
        y = 2.0

        # Clip everything to the rounded bar shape.
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, y, w, h), radius, radius)
        painter.setClipPath(clip)

        for seg in self._segments:
            x0 = seg["start"] * w
            x1 = seg["end"] * w
            color = QColor(Colors.PEAK if seg["peak"] else Colors.OFF_PEAK)
            color.setAlpha(200)
            painter.fillRect(QRectF(x0, y, x1 - x0, h), color)

        painter.setClipping(False)

        # "Now" marker
        x = self._now_fraction * w
        pen = QPen(QColor(Colors.TEXT_PRIMARY), 2)
        painter.setPen(pen)
        painter.drawLine(int(x), int(y - 1), int(x), int(y + h + 1))

        # Hour ticks at 00 / 06 / 12 / 18
        painter.setPen(QColor(Colors.TEXT_MUTED))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        for hour in (0, 6, 12, 18):
            tx = (hour / 24.0) * w
            painter.drawText(
                QRectF(tx - 10, y + h + 1, 20, 12),
                Qt.AlignmentFlag.AlignCenter,
                f"{hour:02d}",
            )
        painter.end()
