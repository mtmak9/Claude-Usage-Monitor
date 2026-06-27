"""Generate the application & status icons programmatically (no design tools).

Produces, in this ``assets`` folder:
    app.png / app.ico            -> application / executable icon
    status_<color>.png           -> green / yellow / orange / red / gray discs

The app icon is a circular **usage gauge** (a ~73 %% progress ring in the app's
green→amber→orange threshold palette on a dark rounded tile) — on brand with the
overlay's gauges, and the open ring doubles as a "C" for Claude.

``app.ico`` is written as a real multi-resolution icon (16…256 px, PNG-compressed
entries) with a tiny built-in writer, so no extra build dependency is needed.

Run directly:  ``python assets/generate_icons.py``
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent

COLORS = {
    "green": "#22c55e",
    "yellow": "#eab308",
    "orange": "#f97316",
    "red": "#ef4444",
    "gray": "#64748b",
}

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


# --------------------------------------------------------------------------- #
# App icon — circular usage gauge on a dark rounded tile
# --------------------------------------------------------------------------- #
def _app_pixmap(size: int = 256) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    s = float(size)

    # --- rounded tile background ---------------------------------------- #
    margin = s * 0.045
    tile = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
    radius = s * 0.225
    bg = QLinearGradient(0, margin, 0, s - margin)
    bg.setColorAt(0.0, QColor("#172033"))
    bg.setColorAt(1.0, QColor("#0b1120"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(tile, radius, radius)
    # hairline top highlight for a subtle "glass" feel
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 22), max(1.0, s * 0.006)))
    p.drawRoundedRect(tile, radius, radius)

    # --- gauge geometry ------------------------------------------------- #
    cx, cy = s / 2.0, s / 2.0
    r = s * 0.295
    thickness = s * 0.125
    ring_rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)

    # soft glow behind the ring
    glow = QRadialGradient(QPointF(cx, cy), r * 1.45)
    glow.setColorAt(0.60, QColor(249, 115, 22, 0))
    glow.setColorAt(0.86, QColor(249, 115, 22, 38))
    glow.setColorAt(1.0, QColor(249, 115, 22, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QRectF(cx - r * 1.45, cy - r * 1.45, r * 2.9, r * 2.9))

    # --- faint full track ----------------------------------------------- #
    track = QPen(QColor(255, 255, 255, 26), thickness)
    track.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(track)
    p.drawArc(ring_rect, 0, 360 * 16)

    # --- value arc (≈73 %), green→amber→orange ------------------------- #
    # Sweeps counter-clockwise from the top so the colour flow matches the
    # conical gradient's CCW direction (green at the top → orange at the cap).
    value = 0.73
    grad = QConicalGradient(cx, cy, 90.0)  # 0.0 at the top
    grad.setColorAt(0.00, QColor("#22c55e"))
    grad.setColorAt(0.40, QColor("#eab308"))
    grad.setColorAt(0.78, QColor("#f97316"))
    grad.setColorAt(1.00, QColor("#f97316"))
    vpen = QPen(QBrush(grad), thickness)
    vpen.setCapStyle(Qt.PenCapStyle.FlatCap)  # avoids the cap straddling the seam
    p.setPen(vpen)
    p.drawArc(ring_rect, 90 * 16, int(360 * value * 16))  # positive = CCW

    # rounded green start cap so the top end looks finished
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#22c55e"))
    p.drawEllipse(QPointF(cx, cy - r), thickness / 2.0, thickness / 2.0)

    # --- end-cap marker (the "current value" dot) ----------------------- #
    import math

    end_deg = 90.0 + 360.0 * value
    rad = math.radians(end_deg)
    ex = cx + r * math.cos(rad)
    ey = cy - r * math.sin(rad)
    cap_r = thickness * 0.60
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#fb923c"))
    p.drawEllipse(QPointF(ex, ey), cap_r, cap_r)
    p.setBrush(QColor(255, 255, 255, 240))
    p.drawEllipse(QPointF(ex, ey), cap_r * 0.40, cap_r * 0.40)

    p.end()
    return pix


def _status_pixmap(color: str, size: int = 256) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size * 0.10
    backing = QColor("#0a0e1a")
    backing.setAlpha(200)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(backing)
    p.drawEllipse(int(m / 2), int(m / 2), int(size - m), int(size - m))
    p.setBrush(QColor(color))
    p.drawEllipse(int(m), int(m), int(size - 2 * m), int(size - 2 * m))
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawEllipse(int(size * 0.30), int(size * 0.24), int(size * 0.22), int(size * 0.16))
    p.end()
    return pix


# --------------------------------------------------------------------------- #
# Multi-resolution .ico writer (PNG-compressed entries; Windows Vista+)
# --------------------------------------------------------------------------- #
def _png_bytes(pix: QPixmap) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _write_ico(path: Path, entries: list[tuple[int, bytes]]) -> None:
    n = len(entries)
    out = struct.pack("<HHH", 0, 1, n)              # ICONDIR
    offset = 6 + 16 * n
    blobs = b""
    for size, png in entries:
        dim = 0 if size >= 256 else size            # 0 means 256 in ICO
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    path.write_bytes(out + blobs)


def main() -> int:
    _app = QApplication.instance() or QApplication(sys.argv)

    # Master PNG (256) for docs / the .desktop / fallback.
    _app_pixmap(256).save(str(ASSETS / "app.png"), "PNG")

    # Real multi-resolution .ico.
    try:
        _write_ico(ASSETS / "app.ico", [(sz, _png_bytes(_app_pixmap(sz))) for sz in ICO_SIZES])
    except Exception as exc:  # pragma: no cover - never fatal for a build
        print(f"Note: multi-size ICO writer failed ({exc}); writing single-size.")
        _app_pixmap(256).save(str(ASSETS / "app.ico"), "ICO")

    for name, color in COLORS.items():
        _status_pixmap(color).save(str(ASSETS / f"status_{name}.png"), "PNG")

    print(f"Icons written to {ASSETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
