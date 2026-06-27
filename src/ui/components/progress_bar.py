"""Animated gradient progress bar.

A rounded track with a green→yellow→orange→red gradient fill.  The ``value``
property is a real Qt property so transitions can be driven by
:class:`QPropertyAnimation` for buttery-smooth updates.
"""
from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

from ..styles.colors import Colors


class GradientProgressBar(QWidget):
    def __init__(self, parent=None, height: int = 10) -> None:
        super().__init__(parent)
        self._value = 0.0           # current (animated) value 0-100
        self._target = 0.0
        self._bar_height = height
        self._gradient_stops = None  # list[(pos, hex)] overriding the default
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(650)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_gradient(self, stops) -> None:
        """Override the fill colours. ``stops`` is ``[(pos0-1, '#hex'), …]`` or
        ``None`` to restore the default usage gradient."""
        self._gradient_stops = stops
        self.update()

    # -- animated property --------------------------------------------- #
    def get_value(self) -> float:
        return self._value

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(100.0, float(v)))
        self.update()

    value = pyqtProperty(float, fget=get_value, fset=set_value)

    def animate_to(self, target: float) -> None:
        self._target = max(0.0, min(100.0, float(target)))
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(self._target)
        self._anim.start()

    # -- painting ------------------------------------------------------- #
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self._bar_height
        radius = h / 2.0
        y = (self.height() - h) / 2.0

        # Track
        track = QRectF(0, y, w, h)
        path = QPainterPath()
        path.addRoundedRect(track, radius, radius)
        painter.fillPath(path, QColor(Colors.BG_TERTIARY))

        if self._value <= 0:
            return

        # Fill, clipped to the rounded track
        fill_w = max(h, w * (self._value / 100.0))
        fill_rect = QRectF(0, y, fill_w, h)
        fill_path = QPainterPath()
        fill_path.addRoundedRect(fill_rect, radius, radius)

        gradient = QLinearGradient(0, 0, w, 0)
        if self._gradient_stops:
            for pos, color in self._gradient_stops:
                gradient.setColorAt(pos, QColor(color))
        else:
            gradient.setColorAt(0.0, QColor(Colors.GREEN))
            gradient.setColorAt(0.55, QColor(Colors.YELLOW))
            gradient.setColorAt(0.80, QColor(Colors.ORANGE))
            gradient.setColorAt(1.0, QColor(Colors.RED))

        painter.setClipPath(path)  # never draw outside the track
        painter.fillPath(fill_path, gradient)
        painter.end()
