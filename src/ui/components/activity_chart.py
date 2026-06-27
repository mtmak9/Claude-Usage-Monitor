"""Mini activity heat-bar chart — intensity of prompts over the last 24 hours."""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

from ..styles.colors import Colors


class ActivityChart(QWidget):
    def __init__(self, parent=None, height: int = 56) -> None:
        super().__init__(parent)
        self._values: List[float] = [0.0] * 24
        self._chart_height = height
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def set_values(self, values: List[float]) -> None:
        if values:
            self._values = [max(0.0, min(1.0, float(v))) for v in values]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        n = len(self._values) or 1
        w = self.width()
        h = self._chart_height
        gap = 2.0
        bar_w = max(2.0, (w - gap * (n - 1)) / n)
        baseline = h - 12  # leave room for an axis label row

        for i, v in enumerate(self._values):
            x = i * (bar_w + gap)
            bar_h = max(2.0, v * (baseline - 2))
            y = baseline - bar_h
            color = QColor(Colors.for_utilization(v * 100))
            color.setAlpha(70 + int(150 * v))
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bar_w, bar_h), 2, 2)
            painter.fillPath(path, color)

        # Axis hint
        painter.setPen(QColor(Colors.TEXT_MUTED))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, baseline + 1, 40, 11),
            Qt.AlignmentFlag.AlignLeft,
            "-24h",
        )
        painter.drawText(
            QRectF(w - 40, baseline + 1, 40, 11),
            Qt.AlignmentFlag.AlignRight,
            "teraz",
        )
        painter.end()
