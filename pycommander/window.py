"""The GUI: a real QTreeView, but showing exactly one level at a time.

The whole menu tree lives in a QStandardItemModel. Drilling down is
`setRootIndex(child)` rather than expanding, so the view renders one level
at a time — the navigation model of the original curses Commander — while
still being a native tree with per-item icons.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
    QStandardItem,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QLabel,
    QMessageBox,
    QStyle,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, UI_POINT_SIZE
from .dialogs import RenameFolderDialog
from .launcher import launch, open_in_editor
from .menu import MenuNode, Options, dump_menu

NODE_ROLE = Qt.ItemDataRole.UserRole

HINTS = "↑↓ move    → open    ← back    ⏎ launch    e edit menu    q quit"

MENU_POINT_SIZE = UI_POINT_SIZE  # local alias: this file spells it out a lot
ICON_SIZE = 28
ROW_PADDING = 10  # px above and below each row's text
TOOLTIP_LINES = 12  # of an inline sh snippet, before the tooltip is truncated

# Right-justified per-row action icons (currently just "edit"). Slots are
# numbered from the row's right edge, 0 = rightmost, so future icons (move
# up/down) can take slots 1, 2, ... without moving this one.
ACTION_ICON_SIZE = 20
ACTION_ICON_MARGIN = 8  # px around and between icons
ACTION_AREA_WIDTH = ACTION_ICON_MARGIN + ACTION_ICON_SIZE + ACTION_ICON_MARGIN
EDIT_SLOT = 0

# The desktop's own highlight color (Ubuntu's #E95420) is loud for something
# you stare at while hunting a menu, so the selection bar is pinned to a
# darker, less saturated orange instead of following the system accent.
HIGHLIGHT_BG = "#9e4b2e"
HIGHLIGHT_FG = "#ffffff"


def _edit_icon() -> QIcon:
    for name in ("document-edit", "gtk-edit", "accessories-text-editor"):
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    # No icon theme has any of those (e.g. a bare desktop install): fall back
    # to a drawn pencil glyph so the button is still visible.
    pixmap = QPixmap(ACTION_ICON_SIZE, ACTION_ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = painter.font()
    font.setPointSize(ACTION_ICON_SIZE - 8)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "✎")
    painter.end()
    return QIcon(pixmap)


class RowActionDelegate(QStyledItemDelegate):
    """Draws the right-justified action icon(s) on top of each normal row."""

    def __init__(self, parent: QTreeView) -> None:
        super().__init__(parent)
        self._edit_icon = _edit_icon()

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        self._edit_icon.paint(painter, self.icon_rect(option.rect, EDIT_SLOT))

    @staticmethod
    def icon_rect(row_rect: QRect, slot: int) -> QRect:
        """Where slot `slot` (0 = rightmost) sits within `row_rect`."""
        right = row_rect.right() - ACTION_ICON_MARGIN - slot * (ACTION_ICON_SIZE + ACTION_ICON_MARGIN)
        top = row_rect.top() + (row_rect.height() - ACTION_ICON_SIZE) // 2
        return QRect(right - ACTION_ICON_SIZE, top, ACTION_ICON_SIZE, ACTION_ICON_SIZE)


class MenuTreeView(QTreeView):
    """One-level-at-a-time tree driven entirely by the arrow keys."""

    level_changed = pyqtSignal()
    launch_failed = pyqtSignal(str)
    edit_requested = pyqtSignal(QModelIndex)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)  # no expand arrows: levels never expand
        self.setItemsExpandable(False)
        self.setExpandsOnDoubleClick(False)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setIndentation(0)
        font = self.font()
        font.setPointSize(MENU_POINT_SIZE)
        self.setFont(font)
        self.setStyleSheet(
            f"QTreeView {{ padding: 6px 0; }}"
            # Extra right padding reserves room for the action icon(s) so
            # a long name elides before it instead of running under them.
            f"QTreeView::item {{ padding: {ROW_PADDING}px {ACTION_AREA_WIDTH}px"
            f" {ROW_PADDING}px 10px; }}"
            # Both :active and :!active, so the bar keeps its color instead of
            # graying out whenever the window loses focus.
            f"QTreeView::item:selected {{"
            f" background: {HIGHLIGHT_BG}; color: {HIGHLIGHT_FG}; }}"
            f"QTreeView::item:selected:!active {{"
            f" background: {HIGHLIGHT_BG}; color: {HIGHLIGHT_FG}; }}"
        )
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(RowActionDelegate(self))
        self.doubleClicked.connect(self._activate)

    # -- model ---------------------------------------------------------------

    def set_nodes(self, nodes: list[MenuNode]) -> None:
        """Build the model from the menu tree and show the top level."""
        model = QStandardItemModel(self)
        self._populate(model.invisibleRootItem(), nodes)
        self.setModel(model)
        self.setRootIndex(QModelIndex())
        self._select_first()
        self.level_changed.emit()

    def _populate(self, parent: QStandardItem, nodes: list[MenuNode]) -> None:
        for node in nodes:
            item = QStandardItem(node.name)
            item.setEditable(False)
            item.setSelectable(True)
            item.setIcon(self._icon_for(node))
            item.setData(node, NODE_ROLE)
            item.setToolTip(_tooltip(node))
            parent.appendRow(item)
            if node.is_section:
                self._populate(item, node.children)

    def _icon_for(self, node: MenuNode) -> QIcon:
        if node.icon:
            path = os.path.expanduser(os.path.expandvars(node.icon))
            icon = QIcon(path) if os.path.isfile(path) else QIcon.fromTheme(node.icon)
            if not icon.isNull():
                return icon
        standard = (
            QStyle.StandardPixmap.SP_DirIcon
            if node.is_section
            else QStyle.StandardPixmap.SP_FileIcon
        )
        return self.style().standardIcon(standard)

    # -- navigation ----------------------------------------------------------

    def node_at(self, index: QModelIndex) -> MenuNode | None:
        return index.data(NODE_ROLE) if index.isValid() else None

    def breadcrumb(self) -> list[str]:
        """Names of the sections we have descended into, outermost first."""
        names: list[str] = []
        index = self.rootIndex()
        while index.isValid():
            names.insert(0, index.data(Qt.ItemDataRole.DisplayRole))
            index = index.parent()
        return names

    def _select_first(self) -> None:
        first = self.model().index(0, 0, self.rootIndex())
        if first.isValid():
            self.setCurrentIndex(first)

    def descend(self, index: QModelIndex) -> None:
        self.setRootIndex(index)
        self._select_first()
        self.level_changed.emit()

    def ascend(self) -> None:
        came_from = self.rootIndex()
        if not came_from.isValid():
            return  # already at the top level; Left does nothing, as in Commander
        self.setRootIndex(came_from.parent())
        # Land the highlight back on the section we just stepped out of.
        self.setCurrentIndex(came_from)
        self.level_changed.emit()

    def _activate(self, index: QModelIndex | None = None) -> None:
        index = index if index is not None and index.isValid() else self.currentIndex()
        node = self.node_at(index)
        if node is None:
            return
        if node.is_section:
            self.descend(index)
        else:
            error = launch(node)
            if error:
                self.launch_failed.emit(error)

    # -- mouse -----------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            if index.isValid():
                icon_rect = RowActionDelegate.icon_rect(self.visualRect(index), EDIT_SLOT)
                if icon_rect.contains(pos):
                    self.edit_requested.emit(index)
                    return  # swallowed: a click on the icon isn't a selection
        super().mousePressEvent(event)

    # -- keys ----------------------------------------------------------------

    def keyboardSearch(self, search: str) -> None:
        """Disabled: plain letters are shortcuts here, not type-ahead."""

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Right:
            node = self.node_at(self.currentIndex())
            if node is not None and node.is_section:
                self.descend(self.currentIndex())
            return  # Right on a script is a deliberate no-op
        if key == Qt.Key.Key_Left:
            self.ascend()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate()
            return
        super().keyPressEvent(event)


class MainWindow(QWidget):
    def __init__(self, menu_path: str, nodes: list[MenuNode], options: Options) -> None:
        super().__init__()
        self.menu_path = menu_path
        self.nodes = nodes
        self.options = options

        self.setWindowTitle(APP_NAME)
        self.resize(560, 640)

        self.header = QLabel()
        self.header.setStyleSheet(
            f"font-weight: bold; font-size: {MENU_POINT_SIZE + 1}pt; padding: 12px 14px;"
        )

        self.tree = MenuTreeView(self)
        self.tree.level_changed.connect(self._update_header)
        self.tree.launch_failed.connect(self._show_launch_error)
        self.tree.edit_requested.connect(self._handle_edit_icon)

        footer = QLabel(HINTS)
        footer.setStyleSheet(f"font-size: {MENU_POINT_SIZE - 3}pt; padding: 10px 14px;")
        footer.setEnabled(False)  # renders in the theme's disabled (dim) color

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.tree, 1)
        layout.addWidget(footer)

        # Shortcuts rather than keyPressEvent: QAbstractItemView swallows plain
        # letter keys (its type-ahead search), so "q" would never reach us here.
        for keys, slot in ((("Esc", "Q"), self.close), (("E",), self.edit_menu)):
            for key in keys:
                QShortcut(QKeySequence(key), self, activated=slot)

        self.tree.set_nodes(nodes)
        self.tree.setFocus()

    def _update_header(self) -> None:
        """Show where we are, or nothing at all at the top level.

        The app's name lives in the title bar; inside the window the header
        earns its space only once we've descended into a section, so at the
        top level it disappears entirely rather than leaving a blank strip.
        """
        crumbs = self.tree.breadcrumb()
        self.header.setText(" / ".join(crumbs))
        self.header.setVisible(bool(crumbs))

    def _show_launch_error(self, message: str) -> None:
        QMessageBox.critical(self, f"{APP_NAME} — launch failed", message)

    def _handle_edit_icon(self, index: QModelIndex) -> None:
        """The row's edit icon was clicked. Only folders have an editor so far."""
        node = self.tree.node_at(index)
        if node is None or not node.is_section:
            return  # scripts: no editor yet, ignore the click
        dialog = RenameFolderDialog(node.name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = dialog.new_name()
        if not new_name or new_name == node.name:
            return
        node.name = new_name
        item = self.tree.model().itemFromIndex(index)
        if item is not None:
            item.setText(new_name)
        error = self._save_menu()
        if error:
            QMessageBox.critical(self, f"{APP_NAME} — cannot save menu", error)

    def _save_menu(self) -> str | None:
        try:
            dump_menu(self.menu_path, self.nodes, self.options)
        except OSError as exc:
            return f"Could not write {self.menu_path}:\n\n{exc}"
        return None

    def edit_menu(self) -> None:
        """Open the menu file itself in the configured editor.

        The window stays open, but nothing re-reads the file — edits take
        effect the next time PyCommander starts.
        """
        error = open_in_editor(self.menu_path, self.options.resolved_editor())
        if error:
            QMessageBox.critical(self, f"{APP_NAME} — cannot edit menu", error)


def _tooltip(node: MenuNode) -> str:
    """What the item points at: a path, the snippet itself, or a child count."""
    if node.sh is not None:
        lines = node.sh.strip().splitlines()
        if len(lines) > TOOLTIP_LINES:
            lines = lines[:TOOLTIP_LINES] + [f"… {len(lines) - TOOLTIP_LINES} more lines"]
        return "\n".join(lines)
    if node.file is not None:
        return node.resolved_file
    return f"{len(node.children)} items"


def format_errors(menu_path: str, errors: list[str]) -> str:
    lines = "\n".join(f"  • {e}" for e in errors)
    return f"{menu_path} has {len(errors)} problem(s):\n\n{lines}"
