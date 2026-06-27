"""Model name badge: a coloured status dot, the model label, and usage text."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ... import constants
from ..styles.colors import Colors


class _Dot(QWidget):
    def __init__(self, parent=None, diameter: int = 10) -> None:
        super().__init__(parent)
        self._color = QColor(Colors.PURPLE)
        self._d = diameter
        self.setFixedSize(diameter + 2, diameter + 2)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, self._d, self._d)
        painter.end()


class ModelBadge(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._dot = _Dot()
        layout.addWidget(self._dot)

        self._name = QLabel("Opus 4.8")
        self._name.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        layout.addWidget(self._name)

        layout.addStretch(1)

        self._usage = QLabel("—")
        self._usage.setObjectName("Secondary")
        self._usage.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self._usage)

    def set_model(self, model_id: str, color: str = Colors.PURPLE) -> None:
        self._name.setText(constants.model_label(model_id))
        self._dot.set_color(color)

    def set_usage(self, primary: str, secondary: str = "") -> None:
        text = primary if not secondary else f"{primary}  |  {secondary}"
        self._usage.setText(text)
