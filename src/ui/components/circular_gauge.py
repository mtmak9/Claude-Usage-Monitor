"""Circular percentage gauge used for the subscription cycle indicator."""
from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..styles.colors import Colors


class CircularGauge(QWidget):
    def __init__(self, parent=None, size: int = 92, thickness: int = 9) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._size = size
        self._thickness = thickness
        self._caption = ""
        self.setFixedSize(size, size)
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_value(self) -> float:
        return self._value

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(100.0, float(v)))
        self.update()

    value = pyqtProperty(float, fget=get_value, fset=set_value)

    def animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(max(0.0, min(100.0, float(target))))
        self._anim.start()

    def set_caption(self, text: str) -> None:
        self._caption = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = self._thickness / 2 + 2
        rect = QRectF(margin, margin, self._size - 2 * margin, self._size - 2 * margin)

        # Background ring
        pen = QPen(QColor(Colors.BG_TERTIARY), self._thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Value arc (start at top, go clockwise)
        color = QColor(Colors.for_utilization(self._value))
        pen.setColor(color)
        painter.setPen(pen)
        span = int(-self._value / 100.0 * 360 * 16)
        painter.drawArc(rect, 90 * 16, span)

        # Centre text — big percentage
        painter.setPen(QColor(Colors.TEXT_PRIMARY))
        font = QFont("Segoe UI", 18, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignCenter, f"{int(round(self._value))}%"
        )

        # Optional caption under the number
        if self._caption:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.setFont(QFont("Segoe UI", 8))
            cap_rect = QRectF(rect.x(), rect.center().y() + 12, rect.width(), 16)
            painter.drawText(cap_rect, Qt.AlignmentFlag.AlignCenter, self._caption)
        painter.end()
