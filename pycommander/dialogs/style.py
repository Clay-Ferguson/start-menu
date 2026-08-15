"""Styling shared by the editing dialogs.

Kept in its own module because both dialogs draw the same bordered frame and
the same lightened input fields; anything only one of them needs lives in
that dialog's own module instead.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from .. import UI_POINT_SIZE

# A plain QDialog's outer edge is easy to lose against the desktop behind it,
# so the real content sits inside a bordered QFrame instead — a QDialog won't
# reliably paint a stylesheet border of its own, but a QFrame always will.
BORDER_STYLE = "#dialogFrame { border: 1px solid #a0a0a0; border-radius: 6px; }"
LABEL_STYLE = f"font-size: {UI_POINT_SIZE}pt;"
BUTTON_STYLE = f"QPushButton {{ font-size: {UI_POINT_SIZE}pt; padding: 8px 20px; }}"


def field_background() -> str:
    """A background a shade lighter than the theme's default input color.

    Computed from the live application palette (rather than a fixed hex)
    so it lightens relative to whatever the desktop theme's own input
    background is, instead of assuming a light or a dark theme. Queried
    lazily — at dialog-build time, not import time — since no theme is
    attached to the palette until QApplication exists.
    """
    base = QApplication.palette().color(QPalette.ColorRole.Base)
    return base.lighter(130).name()


def field_border() -> str:
    """A light-gray border, guaranteed lighter than the field's own
    background so it actually reads as an outline instead of vanishing into
    it. Setting any QSS on a widget (as `field_background` does) opts it
    out of the style's native border too, so this is drawn explicitly
    rather than relying on a native on/off switch.
    """
    return QColor(field_background()).lighter(140).name()


def field_style() -> str:
    """Shared padding/font styling for single-line inputs and the combobox,
    plus the lightened background and border from `field_background` and
    `field_border`."""
    return (
        f"padding: 8px; font-size: {UI_POINT_SIZE}pt;"
        f" background-color: {field_background()}; border: 1px solid {field_border()};"
    )
