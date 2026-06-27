"""QSS stylesheet generation for the dark theme.

Kept as a function so colours stay in one place (:class:`Colors`) and so we can
parametrise opacity / accent later without editing a giant string literal.
"""
from __future__ import annotations

from .colors import Colors


def build_stylesheet() -> str:
    c = Colors
    return f"""
    /* ---- Base ---- */
    QWidget {{
        color: {c.TEXT_PRIMARY};
        font-family: "Segoe UI", "Inter", sans-serif;
        font-size: 12px;
    }}

    /* Top-level dialogs/windows need an explicit dark background (the overlay
       paints its own translucent background and is unaffected). */
    QDialog, QMainWindow {{
        background-color: {c.BG_PRIMARY};
    }}
    QMessageBox {{ background-color: {c.BG_PRIMARY}; }}

    QToolTip {{
        background-color: {c.BG_TERTIARY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER};
        padding: 4px 8px;
        border-radius: 6px;
    }}

    /* ---- Cards / sections ---- */
    QFrame#Card {{
        background-color: {c.BG_SECONDARY};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: 12px;
    }}

    QFrame#Root {{
        background-color: {c.BG_PRIMARY};
        border: 1px solid {c.BORDER};
        border-radius: 16px;
    }}

    QLabel#SectionTitle {{
        color: {c.TEXT_SECONDARY};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
    }}

    QLabel#Muted {{ color: {c.TEXT_MUTED}; font-size: 10px; }}
    QLabel#Secondary {{ color: {c.TEXT_SECONDARY}; }}
    QLabel#BigNumber {{ color: {c.TEXT_PRIMARY}; font-size: 40px; font-weight: 800; }}
    QLabel#Value {{ color: {c.TEXT_PRIMARY}; font-weight: 700; }}

    /* ---- Buttons ---- */
    QPushButton {{
        background-color: {c.BG_TERTIARY};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{ background-color: {c.BG_ELEVATED}; border-color: {c.BLUE}; }}
    QPushButton:pressed {{ background-color: {c.BG_SECONDARY}; }}
    QPushButton#Primary {{
        background-color: {c.BLUE};
        border: none;
        color: white;
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background-color: #2563eb; }}

    /* Small icon buttons (compact / close / show-password).  Flat & borderless
       for a modern overlay-control look — just the glyph, with a subtle hover
       wash.  (The default bordered box reads as dated for header controls.) */
    QPushButton#IconButton {{
        background: transparent;
        border: none;
        border-radius: 7px;
        padding: 0px;
        min-width: 0px;
        color: {c.TEXT_SECONDARY};
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton#IconButton:hover {{
        background: {c.with_alpha("#ffffff", 0.10)};
        color: {c.TEXT_PRIMARY};
    }}
    QPushButton#IconButton:pressed {{
        background: {c.with_alpha("#ffffff", 0.05)};
    }}
    QPushButton#IconButton:checked {{
        background: {c.with_alpha(c.BLUE, 0.18)};
        color: {c.BLUE};
    }}

    /* ---- Tab pills ---- */
    QPushButton#Tab {{
        background-color: transparent;
        border: none;
        color: {c.TEXT_SECONDARY};
        border-radius: 9px;
        padding: 6px 4px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#Tab:hover {{ color: {c.TEXT_PRIMARY}; }}
    QPushButton#Tab:checked {{
        background-color: {c.BLUE};
        color: white;
    }}

    /* ---- Inputs ---- */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {c.BG_TERTIARY};
        border: 1px solid {c.BORDER};
        border-radius: 8px;
        padding: 6px 8px;
        color: {c.TEXT_PRIMARY};
        selection-background-color: {c.BLUE};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {c.BLUE};
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background-color: {c.BG_TERTIARY};
        border: 1px solid {c.BORDER};
        selection-background-color: {c.BLUE};
        color: {c.TEXT_PRIMARY};
    }}

    /* ---- Checkbox ---- */
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 5px;
        border: 1px solid {c.BORDER};
        background: {c.BG_TERTIARY};
    }}
    QCheckBox::indicator:checked {{
        background: {c.BLUE};
        border-color: {c.BLUE};
    }}

    /* ---- Slider ---- */
    QSlider::groove:horizontal {{
        height: 6px; border-radius: 3px;
        background: {c.BG_TERTIARY};
    }}
    QSlider::sub-page:horizontal {{
        background: {c.BLUE}; border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {c.TEXT_PRIMARY};
        width: 16px; height: 16px;
        margin: -6px 0; border-radius: 8px;
    }}

    /* ---- Group box ---- */
    QGroupBox {{
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 8px;
        font-weight: 600;
        color: {c.TEXT_SECONDARY};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px; padding: 0 4px;
    }}

    /* ---- Scrollbars ---- */
    QScrollBar:vertical {{
        background: transparent; width: 8px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c.BG_TERTIARY}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

    /* ---- Table (history window) ---- */
    QTableWidget {{
        background-color: {c.BG_SECONDARY};
        alternate-background-color: {c.BG_ELEVATED};
        gridline-color: {c.BORDER_SUBTLE};
        border: 1px solid {c.BORDER_SUBTLE};
        border-radius: 8px;
        color: {c.TEXT_PRIMARY};
    }}
    QTableWidget::item {{ padding: 2px 6px; }}
    QTableWidget::item:selected {{ background-color: {c.BLUE}; color: white; }}
    QHeaderView::section {{
        background-color: {c.BG_TERTIARY};
        color: {c.TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {c.BORDER};
        padding: 5px 6px;
        font-weight: 600;
    }}
    QTableCornerButton::section {{ background-color: {c.BG_TERTIARY}; border: none; }}

    /* ---- Menu ---- */
    QMenu {{
        background-color: {c.BG_SECONDARY};
        border: 1px solid {c.BORDER};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
    QMenu::item:selected {{ background-color: {c.BLUE}; color: white; }}
    QMenu::separator {{ height: 1px; background: {c.BORDER_SUBTLE}; margin: 4px 8px; }}
    """
