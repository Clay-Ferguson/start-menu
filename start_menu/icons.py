"""Where the window's icons come from, and how they are made the right size.

Every icon the window shows goes through `at_size`, which is what lets the
sizes in `tree.py` and `window.py` be whatever reads best rather than
whatever a desktop icon theme happens to ship.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QStyle

# The size an icon is pulled out of its theme at, before being handed on at
# whatever size the row needs; see `at_size`. Large enough that every
# theme's biggest bitmap is what comes back.
_ICON_SOURCE_SIZE = 256


def edit_icon(size: int) -> QIcon:
    """A pencil, for the row's edit action."""
    for name in ("document-edit", "gtk-edit", "accessories-text-editor"):
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    # No icon theme has any of those (e.g. a bare desktop install).
    return _glyph_icon("✎", size)


def back_icon(style: QStyle | None, size: int) -> QIcon:
    """A left-pointing arrow for the header's "go up a level" button."""
    icon = QIcon.fromTheme("go-previous")
    if not icon.isNull():
        return icon
    if style is not None:
        icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        if not icon.isNull():
            return icon
    return _glyph_icon("←", size)


def _glyph_icon(glyph: str, size: int) -> QIcon:
    """`glyph` drawn as a `size`-px icon, for when no theme has one.

    Drawn rather than left empty, so the button it belongs to is still
    visible and still says what it does.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = painter.font()
    font.setPointSize(size - 8)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)


def at_size(source: QIcon, size: int) -> QIcon:
    """`source` re-wrapped so that it really does render at `size` px.

    An icon theme ships a handful of fixed sizes and Qt's theme-icon engine
    hands back the nearest one rather than the size asked for — and older Qt
    will not scale one *up* at all: ask Yaru for a 32px folder and the Qt 6.4
    the `.deb` runs against returns the 16px file, so the menu came out with
    icons half the size they are here. Pulling the icon at a size every theme
    ships large, and handing that pixmap to a plain pixmap-backed QIcon —
    which has no such scruples, and shrinks whatever it is given — gets the
    size we asked for out of every Qt.
    """
    pixmap = source.pixmap(QSize(_ICON_SOURCE_SIZE, _ICON_SOURCE_SIZE))
    if pixmap.isNull():
        return source
    if pixmap.width() < size:
        # Nothing bigger than `size` exists anywhere in the icon; scaling it up
        # here at least fills the space the row reserves, rather than leaving a
        # small picture adrift in the middle of it.
        pixmap = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    icon = QIcon(pixmap)
    # Register the same picture as the *selected* face too. Left to itself, Qt
    # makes that one up by washing the icon in the palette's Highlight color —
    # the desktop accent, not the orange this app pins its selection bar to
    # (see style.HIGHLIGHT_BG) — so the icon on the current row came out tinted
    # a color nothing else on screen uses, and a different one on each Qt.
    icon.addPixmap(pixmap, QIcon.Mode.Selected)
    return icon
