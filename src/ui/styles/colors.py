"""Centralised colour palette for the dark theme.

Plain hex strings so they can be used both in QSS stylesheets and in
``QColor(Colors.BLUE)`` constructions.
"""
from __future__ import annotations


class Colors:
    # Backgrounds
    BG_PRIMARY = "#0a0e1a"
    BG_SECONDARY = "#111827"
    BG_TERTIARY = "#1e293b"
    BG_ELEVATED = "#172033"

    # Borders / dividers
    BORDER = "#1e3a5f"
    BORDER_SUBTLE = "#1b2538"

    # Text
    TEXT_PRIMARY = "#f1f5f9"
    TEXT_SECONDARY = "#94a3b8"
    TEXT_MUTED = "#64748b"

    # Accents
    BLUE = "#3b82f6"
    GREEN = "#22c55e"
    YELLOW = "#eab308"
    RED = "#ef4444"
    PURPLE = "#8b5cf6"
    ORANGE = "#f97316"
    CYAN = "#06b6d4"

    # Semantic aliases
    OK = GREEN
    WARN = YELLOW
    DANGER = RED
    PEAK = ORANGE
    OFF_PEAK = GREEN

    @staticmethod
    def for_utilization(percent: float) -> str:
        """Return the accent colour matching a 0-100 utilisation value."""
        if percent >= 90:
            return Colors.RED
        if percent >= 80:
            return Colors.ORANGE
        if percent >= 50:
            return Colors.YELLOW
        return Colors.GREEN

    @staticmethod
    def with_alpha(hex_color: str, alpha: float) -> str:
        """Return an ``rgba(...)`` string for a hex colour and 0-1 alpha."""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, alpha)):.3f})"
