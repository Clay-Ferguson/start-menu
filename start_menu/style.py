"""The app's shared look: the selection colors and the dialogs' field styling.

Anything used by more than one module lives here, so a dialog never has to
import `window` or `tree` just for a color. Styling only one module needs
stays in that module. Imports nothing from the package except `UI_POINT_SIZE`.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from . import UI_POINT_SIZE

# The desktop's own highlight color (Ubuntu's #E95420) is loud for something
# you stare at while hunting a menu, so the selection bar is pinned to a
# darker, less saturated orange instead of following the system accent.
HIGHLIGHT_BG = "#9e4b2e"
HIGHLIGHT_FG = "#ffffff"
# A wash of the same orange, for the row under the mouse. The rows are given
# an explicit background (see `MenuTreeView._stylesheet`), which costs them
# the hover the native style would otherwise have drawn, so it is drawn here
# instead.
HOVER_BG = "rgba(158, 75, 46, 56)"

LABEL_STYLE = f"font-size: {UI_POINT_SIZE}pt;"
BUTTON_STYLE = f"QPushButton {{ font-size: {UI_POINT_SIZE}pt; padding: 8px 20px; }}"


def field_background() -> QColor:
    """A background a shade lighter than the theme's default input color.

    Computed from the live application palette (rather than a fixed hex)
    so it lightens relative to whatever the desktop theme's own input
    background is, instead of assuming a light or a dark theme. Queried
    lazily — at dialog-build time, not import time — since no theme is
    attached to the palette until QApplication exists.

    Returned as a QColor rather than a hex string because most of what wants
    it wants the color: `field_border()` derives from it, and the `sh` editor
    hands it to `apply_scrollbars`. Only a stylesheet needs `.name()`.
    """
    base = QApplication.palette().color(QPalette.ColorRole.Base)
    return base.lighter(130)


def field_border() -> str:
    """A border that contrasts with the field's own background, whichever
    direction that has to go. Setting any QSS on a widget (as
    `field_background` does) opts it out of the style's native border too,
    so this is drawn explicitly rather than relying on a native on/off
    switch.

    Lightening is tried first, to stay of a piece with the lightened
    background — but both `lighter()` and `darker()` work in HSV, by scaling
    the value component, so each is a no-op at the end of the scale it is
    heading toward. On a light theme the palette's Base is already white and
    lightening hands back white, leaving an outline indistinguishable from
    the field it is meant to outline; darkening covers that case. On a pure
    black Base (some high-contrast and OLED themes) the value component is
    zero and *neither* direction moves, so the last resort is a fixed gray.
    """
    background = field_background()
    lightened = background.lighter(140)
    if lightened != background:
        return lightened.name()
    darkened = background.darker(115)
    if darkened != background:
        return darkened.name()
    return "#2e2e2e"


def field_style() -> str:
    """Shared padding/font styling for single-line inputs and the combobox,
    plus the lightened background and border from `field_background` and
    `field_border`."""
    return (
        f"padding: 8px; font-size: {UI_POINT_SIZE}pt;"
        f" background-color: {field_background().name()};"
        f" border: 1px solid {field_border()};"
    )
