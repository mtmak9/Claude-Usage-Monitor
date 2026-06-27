"""Usage history window with lightweight, dependency-free charts.

Two QPainter charts:
  * a daily-prompts bar chart (last N days)
  * a session-utilisation line chart (last 24h)
plus a compact table of daily peaks.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..api.models import DailyUsageRecord
from ..i18n import tr
from .styles.colors import Colors


class _BarChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: List[Tuple[str, float]] = []
        self.setMinimumHeight(160)

    def set_data(self, data: List[Tuple[str, float]]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad_left, pad_bottom, pad_top = 8, 22, 8

        if not self._data:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("hist_no_data"))
            painter.end()
            return

        max_v = max((v for _, v in self._data), default=1.0) or 1.0
        n = len(self._data)
        gap = 6
        # Cap the width so a single day doesn't render as one giant block.
        bar_w = min(46.0, max(4.0, (w - pad_left - (n - 1) * gap) / n))
        baseline = h - pad_bottom

        for i, (label, value) in enumerate(self._data):
            x = pad_left + i * (bar_w + gap)
            bar_h = (value / max_v) * (baseline - pad_top)
            y = baseline - bar_h
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bar_w, bar_h), 3, 3)
            painter.fillPath(path, QColor(Colors.BLUE))
            # day label (e.g. "06-26" -> "26")
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(
                QRectF(x - 4, baseline + 2, bar_w + 8, 16),
                Qt.AlignmentFlag.AlignCenter,
                label[-2:],
            )
        painter.end()


class _LineChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._series: List[Tuple[datetime, float]] = []
        self.setMinimumHeight(160)

    def set_series(self, series: List[Tuple[datetime, float]]) -> None:
        self._series = series
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 10
        baseline = h - pad

        # grid lines at 25/50/75/100%
        painter.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1, Qt.PenStyle.DashLine))
        for frac in (0.25, 0.5, 0.75, 1.0):
            y = baseline - frac * (baseline - pad)
            painter.drawLine(pad, int(y), w - pad, int(y))

        if len(self._series) < 2:
            painter.setPen(QColor(Colors.TEXT_MUTED))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, tr("hist_too_few")
            )
            painter.end()
            return

        t0 = self._series[0][0].timestamp()
        t1 = self._series[-1][0].timestamp()
        span = max(1.0, t1 - t0)

        path = QPainterPath()
        for i, (ts, val) in enumerate(self._series):
            x = pad + (ts.timestamp() - t0) / span * (w - 2 * pad)
            y = baseline - (min(100.0, max(0.0, val)) / 100.0) * (baseline - pad)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(QColor(Colors.PURPLE), 2))
        painter.drawPath(path)
        painter.end()


class HistoryWindow(QDialog):
    def __init__(self, history_service, parent=None) -> None:
        super().__init__(parent)
        self.history = history_service
        self.setWindowTitle(tr("hist_title"))
        self.setMinimumSize(560, 560)
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(tr("hist_heading"))
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        head.addWidget(title)
        head.addStretch(1)
        reload_btn = QPushButton(tr("hist_reload"))
        reload_btn.clicked.connect(self.reload)
        head.addWidget(reload_btn)
        root.addLayout(head)

        root.addWidget(self._section_label(tr("hist_daily_prompts")))
        self.bar = _BarChart()
        root.addWidget(self.bar)

        root.addWidget(self._section_label(tr("hist_session_util")))
        self.line = _LineChart()
        root.addWidget(self.line)

        root.addWidget(self._section_label(tr("hist_details")))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            tr("hist_col_date"), tr("hist_col_prompts"),
            tr("hist_col_peak_session"), tr("hist_col_peak_week"),
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def reload(self) -> None:
        records: List[DailyUsageRecord] = self.history.daily_records(days=14)
        self.bar.set_data([(r.date, float(r.total_prompts)) for r in records])
        self.line.set_series(self.history.session_util_series(hours=24))

        self.table.setRowCount(len(records))
        for row, rec in enumerate(reversed(records)):
            self.table.setItem(row, 0, QTableWidgetItem(rec.date))
            self.table.setItem(row, 1, QTableWidgetItem(str(rec.total_prompts)))
            self.table.setItem(
                row, 2, QTableWidgetItem(f"{rec.peak_session_util:.0f}%")
            )
            self.table.setItem(
                row, 3, QTableWidgetItem(f"{rec.peak_week_util:.0f}%")
            )
