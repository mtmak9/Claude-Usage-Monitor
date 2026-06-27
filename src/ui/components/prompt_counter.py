"""Large animated prompt counter with a small "when today" timeline bar."""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...utils import peak_hours
from ..styles.colors import Colors


class _Timeline(QWidget):
    """A thin bar that marks the fractions of the day a prompt was sent."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._marks: List[float] = []
        self.setMinimumHeight(10)
        self.setMaximumHeight(10)

    def set_marks(self, marks: List[float]) -> None:
        self._marks = [m for m in marks if 0.0 <= m <= 1.0]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        radius = h / 2.0

        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.fillPath(track, QColor(Colors.BG_TERTIARY))

        # "now" position — subtle blue tint over the elapsed part of the day.
        now = peak_hours.current_pacific_hour_fraction()
        now_color = QColor(Colors.BLUE)
        now_color.setAlpha(46)  # ~0.18 opacity
        painter.fillRect(QRectF(0, 0, now * w, h), now_color)

        for m in self._marks:
            x = m * w
            painter.fillRect(QRectF(x - 1, 1, 2, h - 2), QColor(Colors.BLUE))
        painter.end()


class PromptCounter(QWidget):
    """Composite: big number on the left, label + timeline on the right."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._display = 0.0
        self._target = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._number = QLabel("0")
        self._number.setObjectName("BigNumber")
        self._number.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._number.setFont(QFont("Segoe UI", 40, QFont.Weight.ExtraBold))
        layout.addWidget(self._number, 0)

        right = QVBoxLayout()
        right.setSpacing(4)
        self._caption = QLabel("promptów dziś")
        self._caption.setObjectName("Secondary")
        right.addStretch(1)
        right.addWidget(self._caption)
        self._timeline = _Timeline()
        right.addWidget(self._timeline)
        right.addStretch(1)
        layout.addLayout(right, 1)

        self._anim = QPropertyAnimation(self, b"display", self)
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # animated display number
    def get_display(self) -> float:
        return self._display

    def set_display(self, v: float) -> None:
        self._display = float(v)
        self._number.setText(str(int(round(self._display))))

    display = pyqtProperty(float, fget=get_display, fset=set_display)

    def set_count(self, count: int, caption: str | None = None) -> None:
        if caption:
            self._caption.setText(caption)
        self._target = int(count)
        self._anim.stop()
        self._anim.setStartValue(self._display)
        self._anim.setEndValue(float(count))
        self._anim.start()

    def set_timeline(self, marks: List[float]) -> None:
        self._timeline.set_marks(marks)
