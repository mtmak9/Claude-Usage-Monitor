"""The always-on-top floating overlay widget — the heart of the app.

Frameless, translucent, draggable.  Renders every usage section:

    TAB BAR  →  PROMPTY  →  MODEL  →  LIMITY  →  SUBSKRYPCJA  →  PEAK  →  AKTYWNOŚĆ

It is purely a *view*: ``update_snapshot`` / ``update_activity`` feed it data and
it animates the change.  No network or storage logic lives here.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import constants
from ..api.models import ActivityData, UsageSnapshot
from .components.activity_chart import ActivityChart
from .components.circular_gauge import CircularGauge
from .components.model_badge import ModelBadge
from .components.peak_indicator import PeakIndicator
from .components.progress_bar import GradientProgressBar
from .components.prompt_counter import PromptCounter
from .styles.colors import Colors

_TAB_LABELS = ("DZIŚ", "TYDZIEŃ", "MIESIĄC")
_PROMPT_CAPTIONS = ("promptów dziś", "promptów w tygodniu", "promptów w miesiącu")


class Overlay(QWidget):
    request_menu = pyqtSignal(QPoint)   # right-click → show context menu

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self._snapshot: Optional[UsageSnapshot] = None
        self._activity: Optional[ActivityData] = None
        self._drag_offset: Optional[QPoint] = None
        self._compact = bool(config.compact)
        self._active_tab = config.active_tab

        self._init_window()
        self._build_ui()
        self._apply_tab(self._active_tab, persist=False)
        self.set_compact(self._compact, persist=False)
        self._restore_position()

    # ------------------------------------------------------------------ #
    # Window setup
    # ------------------------------------------------------------------ #
    def _init_window(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.config.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(self.config.opacity)
        self.setFixedWidth(constants.OVERLAY_WIDTH)
        self.setWindowTitle(constants.APP_NAME)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self.root = QFrame()
        self.root.setObjectName("Root")
        outer.addWidget(self.root)

        root_layout = QVBoxLayout(self.root)
        root_layout.setContentsMargins(14, 12, 14, 14)
        root_layout.setSpacing(10)

        root_layout.addLayout(self._build_header())
        root_layout.addLayout(self._build_tabs())
        self._prompty_card = self._build_prompty()
        root_layout.addWidget(self._prompty_card)
        self._model_card = self._build_model()
        root_layout.addWidget(self._model_card)
        self._limity_card = self._build_limity()
        root_layout.addWidget(self._limity_card)
        self._sub_card = self._build_subscription()
        root_layout.addWidget(self._sub_card)
        self._credits_card = self._build_credits()
        root_layout.addWidget(self._credits_card)
        self._peak_card = self._build_peak()
        root_layout.addWidget(self._peak_card)
        self._activity_card = self._build_activity()
        root_layout.addWidget(self._activity_card)
        root_layout.addStretch(1)

    # -- header --------------------------------------------------------- #
    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        title = QLabel("Claude Usage Monitor")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        row.addWidget(title)
        row.addStretch(1)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        row.addWidget(self._status_dot)

        self._btn_compact = QPushButton("▾")
        self._btn_compact.setObjectName("IconButton")
        self._btn_compact.setFixedSize(24, 24)
        self._btn_compact.setToolTip("Tryb kompaktowy / pełny")
        self._btn_compact.clicked.connect(lambda: self.toggle_compact())
        row.addWidget(self._btn_compact)

        self._btn_close = QPushButton("✕")
        self._btn_close.setObjectName("IconButton")
        self._btn_close.setFixedSize(24, 24)
        self._btn_close.setToolTip("Ukryj (działa dalej w zasobniku)")
        self._btn_close.clicked.connect(self.hide)
        row.addWidget(self._btn_close)
        return row

    # -- tabs ----------------------------------------------------------- #
    def _build_tabs(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        for i, label in enumerate(_TAB_LABELS):
            btn = QPushButton(label)
            btn.setObjectName("Tab")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._tab_group.addButton(btn, i)
            row.addWidget(btn)
        self._tab_group.idClicked.connect(lambda i: self._apply_tab(i))
        return row

    # -- prompty -------------------------------------------------------- #
    def _build_prompty(self) -> QFrame:
        card, layout = self._card("PROMPTY")
        self._prompt_counter = PromptCounter()
        layout.addWidget(self._prompt_counter)
        return card

    # -- model ---------------------------------------------------------- #
    def _build_model(self) -> QFrame:
        card, layout = self._card(None)
        self._model_badge = ModelBadge()
        layout.addWidget(self._model_badge)
        return card

    # -- limity --------------------------------------------------------- #
    def _build_limity(self) -> QFrame:
        card, layout = self._card("LIMITY")

        self._session_bar, self._session_pct, self._session_reset = self._limit_row(
            layout, "SESJA 5H"
        )
        layout.addSpacing(4)
        self._week_bar, self._week_pct, self._week_reset = self._limit_row(
            layout, "TYDZIEŃ 7D"
        )
        return card

    def _limit_row(self, parent_layout: QVBoxLayout, label: str):
        head = QHBoxLayout()
        name = QLabel(label)
        name.setObjectName("SectionTitle")
        head.addWidget(name)
        head.addStretch(1)
        pct = QLabel("0%")
        pct.setObjectName("Value")
        head.addWidget(pct)
        parent_layout.addLayout(head)

        bar = GradientProgressBar(height=10)
        parent_layout.addWidget(bar)

        sub = QHBoxLayout()
        sub.addStretch(1)
        reset = QLabel("—")
        reset.setObjectName("Muted")
        sub.addWidget(reset)
        parent_layout.addLayout(sub)
        return bar, pct, reset

    # -- subscription --------------------------------------------------- #
    def _build_subscription(self) -> QFrame:
        card, layout = self._card("SUBSKRYPCJA")
        row = QHBoxLayout()
        row.setSpacing(14)

        self._sub_gauge = CircularGauge(size=80)
        row.addWidget(self._sub_gauge, 0, Qt.AlignmentFlag.AlignVCenter)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self._sub_status = self._kv(grid, 0, "Status")
        self._sub_cycle = self._kv(grid, 1, "Cykl")
        self._sub_renews = self._kv(grid, 2, "Odnowienie")
        self._sub_left = self._kv(grid, 3, "Pozostało")
        row.addLayout(grid, 1)

        layout.addLayout(row)
        return card

    # -- credits -------------------------------------------------------- #
    def _build_credits(self) -> QFrame:
        card, layout = self._card("KREDYTY $")

        top = QHBoxLayout()
        self._credits_badge = QLabel("—")
        self._credits_badge.setObjectName("Value")
        top.addWidget(self._credits_badge)
        top.addStretch(1)
        self._credits_pct = QLabel("")
        self._credits_pct.setObjectName("Muted")
        top.addWidget(self._credits_pct)
        layout.addLayout(top)

        self._credits_bar = GradientProgressBar(height=8)
        layout.addWidget(self._credits_bar)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self._credits_used = self._kv(grid, 0, "Wydano")
        self._credits_limit = self._kv(grid, 1, "Limit miesięczny")
        self._credits_balance = self._kv(grid, 2, "Saldo")
        layout.addLayout(grid)

        self._credits_hint = QLabel(
            "Włącz „Usage credits” w ustawieniach Claude, aby śledzić saldo."
        )
        self._credits_hint.setObjectName("Muted")
        self._credits_hint.setWordWrap(True)
        self._credits_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px;")
        layout.addWidget(self._credits_hint)
        return card

    def _kv(self, grid: QGridLayout, r: int, key: str) -> QLabel:
        k = QLabel(key)
        k.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px;")
        v = QLabel("—")
        v.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-weight: 700;"
        )
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(k, r, 0)
        grid.addWidget(v, r, 1)
        return v

    # -- peak ----------------------------------------------------------- #
    def _build_peak(self) -> QFrame:
        card, layout = self._card("PEAK HOURS")
        top = QHBoxLayout()
        self._peak_badge = QLabel("OFF-PEAK")
        self._peak_badge.setObjectName("Value")
        self._style_peak_badge(False)
        top.addWidget(self._peak_badge)
        top.addStretch(1)
        self._peak_next = QLabel("—")
        self._peak_next.setObjectName("Muted")
        top.addWidget(self._peak_next)
        layout.addLayout(top)

        self._peak_bar = PeakIndicator()
        layout.addWidget(self._peak_bar)
        return card

    def _style_peak_badge(self, is_peak: bool) -> None:
        color = Colors.PEAK if is_peak else Colors.OFF_PEAK
        self._peak_badge.setText("PEAK" if is_peak else "OFF-PEAK")
        self._peak_badge.setStyleSheet(
            f"color: {color}; font-weight: 800; letter-spacing: 1px;"
            f"background: {Colors.with_alpha(color, 0.14)};"
            f"border-radius: 7px; padding: 2px 10px;"
        )

    # -- activity ------------------------------------------------------- #
    def _build_activity(self) -> QFrame:
        card, layout = self._card("AKTYWNOŚĆ")
        self._activity_chart = ActivityChart()
        layout.addWidget(self._activity_chart)
        return card

    # -- card helper ---------------------------------------------------- #
    def _card(self, title: Optional[str]):
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        if title:
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            layout.addWidget(label)
        return card, layout

    # ------------------------------------------------------------------ #
    # Data updates
    # ------------------------------------------------------------------ #
    def update_snapshot(self, snap: UsageSnapshot) -> None:
        self._snapshot = snap
        if snap is None:
            return

        if not snap.ok:
            self._status_dot.setStyleSheet(f"color: {Colors.RED};")
            self._status_dot.setToolTip(f"Błąd: {snap.error}")
            self._model_badge.set_usage("offline", snap.error or "")
            return

        self._status_dot.setStyleSheet(f"color: {Colors.GREEN};")
        self._status_dot.setToolTip("Połączono")

        # Model badge
        worst = snap.worst_percent
        self._model_badge.set_model(snap.model, Colors.for_utilization(worst))
        self._model_badge.set_usage(
            f"{int(round(snap.session_percent))}%", f"tydz {int(round(snap.week_percent))}%"
        )

        # Limity
        self._session_bar.animate_to(snap.session_percent)
        self._session_pct.setText(f"{int(round(snap.session_percent))}%")
        self._session_pct.setStyleSheet(
            f"color: {Colors.for_utilization(snap.session_percent)}; font-weight:700;"
        )
        self._session_reset.setText(f"reset {snap.session_reset_text}")

        self._week_bar.animate_to(snap.week_percent)
        self._week_pct.setText(f"{int(round(snap.week_percent))}%")
        self._week_pct.setStyleSheet(
            f"color: {Colors.for_utilization(snap.week_percent)}; font-weight:700;"
        )
        self._week_reset.setText(f"reset {snap.week_reset_text}")

        # Subscription
        self._sub_gauge.animate_to(snap.subscription_percent)
        self._sub_status.setText(snap.plan_name)
        self._sub_cycle.setText(snap.cycle_label)
        self._sub_renews.setText(snap.cycle_renews_text.replace("za ", ""))
        self._sub_left.setText(f"{int(round(100 - snap.subscription_percent))}%")

        # Kredyty ($)
        if snap.credits_enabled:
            self._credits_badge.setText("Włączone")
            self._credits_badge.setStyleSheet(f"color: {Colors.GREEN}; font-weight:700;")
            self._credits_pct.setText(f"{int(round(snap.credits_percent))}% limitu")
            self._credits_bar.show()
            self._credits_hint.hide()
            self._credits_used.setText(snap.credits_used_text)
            self._credits_limit.setText(snap.credits_limit_text)
            self._credits_balance.setText(snap.credits_balance_text)
        else:
            # Feature off in the Claude account → the usage API returns no
            # balance/limit, so say so plainly instead of showing blank dashes.
            self._credits_badge.setText("Wyłączone")
            self._credits_badge.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-weight:700;")
            self._credits_pct.setText("")
            self._credits_bar.hide()
            self._credits_hint.show()
            self._credits_used.setText(snap.credits_used_text)   # API still gives $ spent
            self._credits_limit.setText("—")
            self._credits_balance.setText("—")

        # Peak
        self._style_peak_badge(snap.is_peak)
        self._peak_bar.refresh()
        from ..utils import peak_hours

        self._peak_next.setText(peak_hours.next_transition_text())

    def update_activity(self, activity: ActivityData) -> None:
        self._activity = activity
        if activity is None:
            return
        self._activity_chart.set_values(activity.hourly)
        self._prompt_counter.set_timeline(activity.timeline)
        self._refresh_prompt_count()

    def _refresh_prompt_count(self) -> None:
        if not self._activity:
            return
        count = self._activity.prompts_for_tab(self._active_tab)
        self._prompt_counter.set_count(count, _PROMPT_CAPTIONS[self._active_tab])

    def refresh_dynamic(self) -> None:
        """Called ~1/s to keep countdowns and the peak marker current."""
        self._peak_bar.refresh()
        if self._snapshot and self._snapshot.ok:
            self._session_reset.setText(f"reset {self._snapshot.session_reset_text}")
            self._week_reset.setText(f"reset {self._snapshot.week_reset_text}")
            self._sub_renews.setText(
                self._snapshot.cycle_renews_text.replace("za ", "")
            )

    # ------------------------------------------------------------------ #
    # Tabs & compact mode
    # ------------------------------------------------------------------ #
    def _apply_tab(self, index: int, persist: bool = True) -> None:
        self._active_tab = index
        btn = self._tab_group.button(index)
        if btn:
            btn.setChecked(True)
        self._refresh_prompt_count()
        if persist:
            self.config.set("display.active_tab", index)
            self.config.save()

    def toggle_compact(self) -> None:
        self.set_compact(not self._compact)

    def set_compact(self, compact: bool, persist: bool = True) -> None:
        self._compact = compact
        for card in (
            self._sub_card,
            self._credits_card,
            self._peak_card,
            self._activity_card,
            self._model_card,
        ):
            card.setVisible(not compact)
        self._btn_compact.setText("▴" if compact else "▾")
        self._fit_height()
        if persist:
            self.config.compact = compact
            self.config.save()

    def _fit_height(self) -> None:
        """Resize the frameless window to exactly fit its visible content."""
        self.setFixedWidth(constants.OVERLAY_WIDTH)
        # Both the inner card layout and the outer layout must be invalidated
        # synchronously, otherwise sizeHint() reports a stale (pre-hide) height
        # until the next event-loop pass.
        for layout in (self.root.layout(), self.layout()):
            if layout is not None:
                layout.invalidate()
                layout.activate()
        # setFixedHeight guarantees the top-level window shrinks/grows to the
        # content height (adjustSize() does not reliably shrink a shown window).
        self.setFixedHeight(self.sizeHint().height())

    def is_compact(self) -> bool:
        return self._compact

    def apply_opacity(self, opacity: float) -> None:
        self.setWindowOpacity(max(0.30, min(1.0, opacity)))

    def apply_always_on_top(self, on_top: bool) -> None:
        flags = self.windowFlags()
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    # ------------------------------------------------------------------ #
    # Position persistence + dragging
    # ------------------------------------------------------------------ #
    def _restore_position(self) -> None:
        x, y = self.config.window_pos
        if x >= 0 and y >= 0:
            self.move(x, y)
        else:
            self._place_top_right()

    def _place_top_right(self) -> None:
        screen = self.screen() or (self.parent().screen() if self.parent() else None)
        try:
            from PyQt6.QtWidgets import QApplication

            geo = (screen or QApplication.primaryScreen()).availableGeometry()
            self.move(
                geo.right() - constants.OVERLAY_WIDTH - constants.WINDOW_MARGIN,
                geo.top() + constants.WINDOW_MARGIN,
            )
        except Exception:
            self.move(900, 60)

    def _save_position(self) -> None:
        self.config.set_window_pos(self.x(), self.y())
        self.config.save()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.request_menu.emit(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            self._save_position()
            event.accept()

    def closeEvent(self, event):  # noqa: N802
        # Hide instead of quitting — the app lives in the tray.
        self._save_position()
        event.ignore()
        self.hide()
