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
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
    QStandardItem,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
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
from .menu import MenuNode, Options, dump_menu, load_menu

NODE_ROLE = Qt.ItemDataRole.UserRole

HINTS = "⏎ launch    e edit menu    q quit"

MENU_POINT_SIZE = UI_POINT_SIZE  # local alias: this file spells it out a lot
ICON_SIZE = 28
ROW_PADDING = 10  # px above and below each row's text
TOOLTIP_LINES = 12  # of an inline sh snippet, before the tooltip is truncated

# Right-justified per-row action icons. Slots are numbered from the row's
# right edge, 0 = rightmost, so new icons can join without moving the old
# ones. Left to right on screen: move up, move down, edit.
ACTION_ICON_SIZE = 20
ACTION_ICON_MARGIN = 8  # px around and between icons
EDIT_SLOT = 0
DOWN_SLOT = 1
UP_SLOT = 2
ACTION_SLOT_COUNT = 3
ACTION_AREA_WIDTH = ACTION_ICON_MARGIN + ACTION_SLOT_COUNT * (ACTION_ICON_SIZE + ACTION_ICON_MARGIN)

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
    """Draws the right-justified action icon(s) on top of the current row.

    Only while the view's edit mode is on, and only on the highlighted row —
    otherwise the row paints exactly as it did before this feature existed.
    Which icons apply to a given row (an item at the top of its level has no
    "up", etc.) is decided by the view's `visible_action_slots`, not here.
    """

    def __init__(self, parent: QTreeView) -> None:
        super().__init__(parent)
        self._icons = {
            "edit": _edit_icon(),
            "up": parent.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp),
            "down": parent.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
        }

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        view = self.parent()
        if not getattr(view, "edit_mode", False) or index != view.currentIndex():
            return
        for slot, kind in view.visible_action_slots(index).items():
            self._icons[kind].paint(painter, self.icon_rect(option.rect, slot))

    @staticmethod
    def icon_rect(row_rect: QRect, slot: int) -> QRect:
        """Where slot `slot` (0 = rightmost) sits within `row_rect`."""
        right = row_rect.right() - ACTION_ICON_MARGIN - slot * (ACTION_ICON_SIZE + ACTION_ICON_MARGIN)
        top = row_rect.top() + (row_rect.height() - ACTION_ICON_SIZE) // 2
        return QRect(right - ACTION_ICON_SIZE, top, ACTION_ICON_SIZE, ACTION_ICON_SIZE)


class ToggleSwitch(QAbstractButton):
    """A small on/off switch, styled like a mobile settings toggle.

    QCheckBox's indicator is themed by the desktop's QStyle and awkward to
    reshape into a switch; a bare checkable QAbstractButton with its own
    paintEvent gives full control over the track/knob look instead.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 22)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        track_color = QColor(HIGHLIGHT_BG if self.isChecked() else "#888888")
        painter.setBrush(track_color)
        radius = self.height() / 2
        painter.drawRoundedRect(self.rect(), radius, radius)

        knob_diameter = self.height() - 4
        knob_x = self.width() - knob_diameter - 2 if self.isChecked() else 2
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(int(knob_x), 2, knob_diameter, knob_diameter)


class MenuTreeView(QTreeView):
    """One-level-at-a-time tree driven entirely by the arrow keys."""

    level_changed = pyqtSignal()
    launch_failed = pyqtSignal(str)
    edit_requested = pyqtSignal(QModelIndex)
    move_up_requested = pyqtSignal(QModelIndex)
    move_down_requested = pyqtSignal(QModelIndex)

    # Which signal to emit for each action kind `visible_action_slots` hands out.
    _ACTION_SIGNALS = {"edit": "edit_requested", "up": "move_up_requested", "down": "move_down_requested"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.edit_mode = False  # off by default; never persisted across runs
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
        self.setStyleSheet(self._stylesheet())
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(RowActionDelegate(self))
        self.doubleClicked.connect(self._activate)

    def _stylesheet(self) -> str:
        # Right padding only reserves room for the action icon(s) while edit
        # mode is on; off, rows use the full width, same as before this
        # feature existed.
        right_padding = ACTION_AREA_WIDTH if self.edit_mode else 10
        return (
            f"QTreeView {{ padding: 6px 0; }}"
            f"QTreeView::item {{ padding: {ROW_PADDING}px {right_padding}px"
            f" {ROW_PADDING}px 10px; }}"
            # Both :active and :!active, so the bar keeps its color instead of
            # graying out whenever the window loses focus.
            f"QTreeView::item:selected {{"
            f" background: {HIGHLIGHT_BG}; color: {HIGHLIGHT_FG}; }}"
            f"QTreeView::item:selected:!active {{"
            f" background: {HIGHLIGHT_BG}; color: {HIGHLIGHT_FG}; }}"
        )

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = enabled
        self.setStyleSheet(self._stylesheet())
        self.viewport().update()

    # -- model ---------------------------------------------------------------

    def set_nodes(
        self,
        nodes: list[MenuNode],
        restore_path: list[int] | None = None,
        select_name: str | None = None,
    ) -> None:
        """Build the model from the menu tree.

        With no `restore_path`, this is a fresh load: show the top level.
        With one — as after an edit that rewrote the file and reloaded it —
        descend back to the same folder instead of landing back at the top,
        and highlight `select_name` there instead of always the first row —
        a move only reorders rows, so the item that was highlighted (which
        may not even be the one that moved) needs to be found by name, not
        by the row position it used to be at.
        """
        model = QStandardItemModel(self)
        self._populate(model.invisibleRootItem(), nodes)
        self.setModel(model)
        if restore_path is not None:
            self._restore_path(restore_path, select_name)
        else:
            self.setRootIndex(QModelIndex())
            self._select_first()
            self.level_changed.emit()

    def current_path(self) -> list[int]:
        """Row numbers from the top level down to the current folder.

        The inverse of `_restore_path`: capture this before an edit rebuilds
        the model, then hand it back to `set_nodes` to return to the same
        place.
        """
        rows: list[int] = []
        index = self.rootIndex()
        while index.isValid():
            rows.insert(0, index.row())
            index = index.parent()
        return rows

    def current_selection_name(self) -> str | None:
        """The highlighted row's name, to hand to `set_nodes` as `select_name`."""
        node = self.node_at(self.currentIndex())
        return node.name if node is not None else None

    def _restore_path(self, path: list[int], select_name: str | None) -> None:
        index = QModelIndex()
        for row in path:
            child = self.model().index(row, 0, index)
            if not child.isValid():
                break  # the path no longer exists; land as deep as it goes
            index = child
        self.setRootIndex(index)
        self._select_by_name(select_name)
        self.level_changed.emit()

    def _select_by_name(self, name: str | None) -> None:
        if name is not None:
            for row in range(self.model().rowCount(self.rootIndex())):
                candidate = self.model().index(row, 0, self.rootIndex())
                if candidate.data(Qt.ItemDataRole.DisplayRole) == name:
                    self.setCurrentIndex(candidate)
                    return
        self._select_first()  # no name given, or it's no longer in this level

    def visible_action_slots(self, index: QModelIndex) -> dict[int, str]:
        """Which action icons apply to `index`'s row, and each one's slot.

        The first item in a level has no "up" and the last has no "down" —
        there's nowhere for either to go.
        """
        slots: dict[int, str] = {EDIT_SLOT: "edit"}
        row = index.row()
        count = self.model().rowCount(index.parent())
        if row > 0:
            slots[UP_SLOT] = "up"
        if row < count - 1:
            slots[DOWN_SLOT] = "down"
        return slots

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
        if self.edit_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            # Action icons are only drawn on the current row, so only that
            # row's click can land on one; elsewhere this is a plain select.
            if index.isValid() and index == self.currentIndex():
                row_rect = self.visualRect(index)
                for slot, kind in self.visible_action_slots(index).items():
                    if RowActionDelegate.icon_rect(row_rect, slot).contains(pos):
                        getattr(self, self._ACTION_SIGNALS[kind]).emit(index)
                        return  # swallowed: a click on an icon isn't a selection
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
        self.tree.move_up_requested.connect(lambda index: self._handle_move(index, -1))
        self.tree.move_down_requested.connect(lambda index: self._handle_move(index, 1))

        self.edit_toggle = ToggleSwitch(self)
        self.edit_toggle.toggled.connect(self.tree.set_edit_mode)

        edit_label = QLabel("Edit")
        edit_label.setStyleSheet(f"font-size: {MENU_POINT_SIZE - 3}pt;")

        hints = QLabel(HINTS)
        hints.setStyleSheet(f"font-size: {MENU_POINT_SIZE - 3}pt;")
        hints.setEnabled(False)  # renders in the theme's disabled (dim) color

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 10, 14, 10)
        footer_layout.setSpacing(8)
        footer_layout.addWidget(self.edit_toggle)
        footer_layout.addWidget(edit_label)
        footer_layout.addStretch(1)
        footer_layout.addWidget(hints)

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
        self._save_and_reload()

    def _handle_move(self, index: QModelIndex, delta: int) -> None:
        """The row's move up/down icon was clicked; `delta` is -1 or +1."""
        siblings = self._sibling_list(index)
        pos = index.row()
        new_pos = pos + delta
        if not (0 <= new_pos < len(siblings)):
            return  # the icon shouldn't have been shown at all; ignore it
        siblings[pos], siblings[new_pos] = siblings[new_pos], siblings[pos]
        self._save_and_reload()

    def _sibling_list(self, index: QModelIndex) -> list[MenuNode]:
        """The MenuNode list `index`'s node lives in.

        `self.nodes` for a top-level item, or its parent section's
        `children` otherwise — found by walking the same row-path down
        `self.nodes` that the model index describes.
        """
        rows: list[int] = []
        parent = index.parent()
        while parent.isValid():
            rows.insert(0, parent.row())
            parent = parent.parent()
        siblings = self.nodes
        for row in rows:
            siblings = siblings[row].children
        return siblings

    def _save_and_reload(self) -> None:
        """Write `self.nodes`/`options` out, then reload from disk.

        Rather than patch the tree view's model in place, this takes the
        same one-way trip through `load_menu` that startup does — simpler
        to get right, and it guarantees the GUI matches what's actually on
        disk. The user's current folder and highlighted row are both
        preserved across the rebuild.
        """
        path = self.tree.current_path()
        select_name = self.tree.current_selection_name()
        try:
            dump_menu(self.menu_path, self.nodes, self.options)
        except OSError as exc:
            QMessageBox.critical(
                self, f"{APP_NAME} — cannot save menu", f"Could not write {self.menu_path}:\n\n{exc}"
            )
            return

        nodes, options, errors = load_menu(self.menu_path)
        if errors:
            QMessageBox.critical(
                self, f"{APP_NAME} — cannot reload menu", format_errors(self.menu_path, errors)
            )
            return
        self.nodes = nodes
        self.options = options
        self.tree.set_nodes(nodes, restore_path=path, select_name=select_name)

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
