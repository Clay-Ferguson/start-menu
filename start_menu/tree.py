"""The menu itself: a real QTreeView, but showing exactly one level at a time.

The whole menu tree lives in a QStandardItemModel. Drilling down is
`setRootIndex(child)` rather than expanding, so the view renders one level
at a time — while still being a native tree with per-item icons.

This is only the view. It says what the user asked for through signals —
launch this node, edit or delete or move that row — and `MainWindow` does it.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QTreeView,
    QWidget,
)
from windowchrome import apply_scrollbars

from . import UI_POINT_SIZE
from .icons import at_size, edit_icon
from .menu import LAUNCH_TMUX, MenuNode
from .style import HIGHLIGHT_BG, HIGHLIGHT_FG, HOVER_BG

NODE_ROLE = Qt.ItemDataRole.UserRole

# A menu item's own icon. 32 rather than a rounder-looking number because it
# is a size the desktop icon themes actually ship a bitmap for (16/24/32/48):
# anything between those is the same picture stretched, and looks it.
ICON_SIZE = 32
ROW_PADDING = 10  # px above and below each row's text
TOOLTIP_LINES = 12  # of an inline sh snippet, before the tooltip is truncated

# Right-justified per-row action icons. Slots are numbered from the row's
# right edge, 0 = rightmost, so new icons can join without moving the old
# ones. Left to right on screen: move up, move down, edit, delete.
# `at_size` decouples these from the sizes an icon theme actually ships, so
# the number here is free to be whatever reads best on the row.
ACTION_ICON_SIZE = 28
ACTION_ICON_MARGIN = 8  # px around and between icons
DELETE_SLOT = 0
EDIT_SLOT = 1
DOWN_SLOT = 2
UP_SLOT = 3
ACTION_SLOT_COUNT = 4
ACTION_AREA_WIDTH = ACTION_ICON_MARGIN + ACTION_SLOT_COUNT * (
    ACTION_ICON_SIZE + ACTION_ICON_MARGIN
)


class RowActionDelegate(QStyledItemDelegate):
    """Draws the right-justified action icon(s) on top of the current row.

    Only while the view's edit mode is on, and only on the highlighted row —
    otherwise the row paints exactly as it did before this feature existed.
    Which icons apply to a given row (an item at the top of its level has no
    "up", etc.) is decided by the view's `visible_action_slots`, not here.
    """

    def __init__(self, parent: MenuTreeView) -> None:
        super().__init__(parent)
        self._view = parent
        # `at_size` on each: a desktop icon theme ships a handful of fixed
        # sizes and Qt hands back the nearest one rather than the size asked
        # for, so without it these come out at whatever the theme happens to
        # have (16px, most often) instead of ACTION_ICON_SIZE.
        self._icons = {
            kind: at_size(icon, ACTION_ICON_SIZE)
            for kind, icon in (
                ("edit", edit_icon(ACTION_ICON_SIZE)),
                ("delete", parent.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)),
                ("up", parent.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)),
                ("down", parent.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)),
            )
        }

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        view = self._view
        if not view.edit_mode or index != view.currentIndex():
            return
        for slot, kind in view.visible_action_slots(index).items():
            self._icons[kind].paint(painter, self.icon_rect(option.rect, slot))

    @staticmethod
    def icon_rect(row_rect: QRect, slot: int) -> QRect:
        """Where slot `slot` (0 = rightmost) sits within `row_rect`."""
        step = ACTION_ICON_SIZE + ACTION_ICON_MARGIN
        right = row_rect.right() - ACTION_ICON_MARGIN - slot * step
        top = row_rect.top() + (row_rect.height() - ACTION_ICON_SIZE) // 2
        return QRect(right - ACTION_ICON_SIZE, top, ACTION_ICON_SIZE, ACTION_ICON_SIZE)


class MenuTreeView(QTreeView):
    """One-level-at-a-time tree driven entirely by the arrow keys."""

    level_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    launch_requested = pyqtSignal(object)  # the MenuNode of a script to run
    edit_requested = pyqtSignal(QModelIndex)
    delete_requested = pyqtSignal(QModelIndex)
    move_up_requested = pyqtSignal(QModelIndex)
    move_down_requested = pyqtSignal(QModelIndex)

    # Which signal to emit for each action kind `visible_action_slots` hands out.
    _ACTION_SIGNALS = {
        "edit": "edit_requested",
        "delete": "delete_requested",
        "up": "move_up_requested",
        "down": "move_down_requested",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.edit_mode = False  # off by default; never persisted across runs
        # Menu items share a handful of icons between them (nearly always just
        # the standard folder and file), and `at_size` does real work to build
        # one, so they are built once per distinct `icon:` and reused.
        self._icon_cache: dict[str, QIcon] = {}
        self._hidden_ids: set[int] = set()  # id()s of the nodes a pending cut hides
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)  # no expand arrows: levels never expand
        self.setItemsExpandable(False)
        self.setExpandsOnDoubleClick(False)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setIndentation(0)
        font = self.font()
        font.setPointSize(UI_POINT_SIZE)
        self.setFont(font)
        self.setStyleSheet(self._stylesheet())
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The menu *is* the application, so its own scroll bar is the one that
        # matters most: drawn at twice the desktop's thickness so a long level
        # is easy to drag through. No `base` — unlike the dialogs' input
        # fields, the rows sit on the palette's own Base, which is what
        # `apply_scrollbars` assumes. It goes on the view's scroll bar children,
        # so `_stylesheet()` below can keep being re-applied to the view itself
        # (edit mode toggles it) without disturbing the bars.
        apply_scrollbars(self)
        self.setItemDelegate(RowActionDelegate(self))
        self.doubleClicked.connect(self._activate)

    def _stylesheet(self) -> str:
        # Right padding only reserves room for the action icon(s) while edit
        # mode is on; off, rows use the full width, same as before this
        # feature existed.
        right_padding = ACTION_AREA_WIDTH if self.edit_mode else 10
        return (
            f"QTreeView {{ padding: 6px 0; }}"
            # `background` looks redundant next to a transparent row, but it is
            # what makes the padding apply at all. Qt hands a row back to the
            # native style to paint whenever the item rule has nothing of its
            # own to draw, and the native painter knows nothing about the
            # rule's padding — which on the Qt 6.4 the `.deb` runs against left
            # the indent showing on the selected row only, the one row whose
            # rule *does* carry a background. Naming one here, even an
            # invisible one, puts every row on the same painting path.
            f"QTreeView::item {{ background: transparent;"
            f" padding: {ROW_PADDING}px {right_padding}px {ROW_PADDING}px 10px; }}"
            f"QTreeView::item:hover {{ background: {HOVER_BG}; }}"
            # After :hover, so the selected row keeps its full-strength bar
            # when the mouse is over it; both rules are equally specific, so
            # this is decided by which comes last.
            # Both :active and :!active, so the bar keeps its color instead of
            # graying out whenever the window loses focus.
            f"QTreeView::item:selected {{"
            f" background: {HIGHLIGHT_BG}; color: {HIGHLIGHT_FG}; }}"
            f"QTreeView::item:selected:!active {{"
            f" background: {HIGHLIGHT_BG}; color: {HIGHLIGHT_FG}; }}"
        )

    def set_edit_mode(self, enabled: bool) -> None:
        """Turn the per-row action icons — and multi-selection — on or off.

        Multi-selection exists only to feed Cut, so it's confined to edit
        mode; leaving it, the highlight collapses back to the single current
        row, the way it behaves everywhere else in the app.
        """
        self.edit_mode = enabled
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
            if enabled
            else QAbstractItemView.SelectionMode.SingleSelection
        )
        if not enabled:
            current = self.currentIndex()
            self.clearSelection()
            if current.isValid():
                self.setCurrentIndex(current)
        self.setStyleSheet(self._stylesheet())
        self.viewport().update()

    # -- model ---------------------------------------------------------------

    def set_nodes(
        self,
        nodes: list[MenuNode],
        restore_path: list[str] | None = None,
        select_name: str | None = None,
    ) -> None:
        """Build the model from the menu tree.

        With no `restore_path`, this is a fresh load: show the top level.
        With one — the folder names from `breadcrumb()`, as after an edit that
        rewrote the file and reloaded it — descend back to the same folder
        instead of landing back at the top, and highlight `select_name` there
        instead of always the first row. Both are names rather than row
        numbers because an edit can renumber the rows underneath them: a move
        reorders a level, and a paste empties rows out of the level it cut
        from, which would shift the folder we're standing in. The price is
        that when two siblings share a name, the first of them is the one
        found — accepted, since a menu with twin names is ambiguous to the
        user as well.
        """
        model = QStandardItemModel(self)
        root = model.invisibleRootItem()
        assert root is not None  # a model always has one; the stubs say Optional
        self._populate(root, nodes)
        self.setModel(model)
        # A rebuild replaces every MenuNode object, so a pending cut can't
        # outlive it (MainWindow drops the cut before getting here); start the
        # new model with nothing hidden.
        self._hidden_ids = set()
        # setModel installs a brand new selection model, so this connection has
        # to be remade every time rather than once in __init__.
        self.selectionModel().selectionChanged.connect(
            lambda *_: self.selection_changed.emit()
        )
        if restore_path is not None:
            self._restore_path(restore_path, select_name)
        else:
            self.setRootIndex(QModelIndex())
            self._select_first()
            self.level_changed.emit()

    def current_path(self) -> list[int]:
        """Row numbers from the top level down to the current folder.

        The same walk `breadcrumb()` does, in row numbers instead of names,
        for callers that need to find the matching MenuNode list (see
        `MainWindow._current_level_nodes`). Only valid until the tree is
        mutated; to *return* to this folder after a rebuild, use the names
        from `breadcrumb()` instead.
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

    def _restore_path(self, path: list[str], select_name: str | None) -> None:
        index = QModelIndex()
        for name in path:
            child = self._child_named(index, name)
            if child is None:
                break  # the path no longer exists; land as deep as it goes
            index = child
        self.setRootIndex(index)
        self._select_by_name(select_name)
        self.level_changed.emit()

    def _child_named(self, parent: QModelIndex, name: str) -> QModelIndex | None:
        """`parent`'s first visible child row labelled `name`, if any."""
        for row in range(self.model().rowCount(parent)):
            if self.isRowHidden(row, parent):
                continue
            child = self.model().index(row, 0, parent)
            if child.data(Qt.ItemDataRole.DisplayRole) == name:
                return child
        return None

    def _select_by_name(self, name: str | None) -> None:
        if name is not None:
            child = self._child_named(self.rootIndex(), name)
            if child is not None:
                self.clearSelection()
                self.setCurrentIndex(child)
                return
        self._select_first()  # no name given, or it's no longer in this level

    # -- cut/paste -----------------------------------------------------------

    def set_hidden_nodes(self, nodes: list[MenuNode]) -> None:
        """Hide the rows of `nodes` — the items waiting to be pasted.

        The rows are hidden with `setRowHidden` rather than left out of the
        model, because every edit path here maps a view row back to a MenuNode
        by row number (see `MainWindow._current_level_nodes`): the model has to
        keep the same shape as the tree even while some of its rows aren't on
        screen. Nothing is written to disk by a cut, so this hiding *is* the
        only feedback the user gets that the items are on their way somewhere.
        """
        self._hidden_ids = {id(node) for node in nodes}
        self._apply_hidden(QModelIndex())
        current = self.currentIndex()
        if not current.isValid() or self.isRowHidden(current.row(), current.parent()):
            self._select_first()  # the highlighted row was one of the cut ones

    def _apply_hidden(self, parent: QModelIndex) -> None:
        """Sync every row's hidden state under `parent` with `_hidden_ids`."""
        model = self.model()
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            node = self.node_at(index)
            self.setRowHidden(row, parent, node is not None and id(node) in self._hidden_ids)
            self._apply_hidden(index)

    def selected_nodes(self) -> list[MenuNode]:
        """The nodes selected in the level currently on screen, in row order.

        Selecting rows and then navigating elsewhere would otherwise leave a
        selection hanging on another level; only this level's rows count.
        """
        model = self.selectionModel()
        if model is None:
            return []
        root = self.rootIndex()
        rows = sorted(
            (index for index in model.selectedRows() if index.parent() == root),
            key=lambda index: index.row(),
        )
        return [node for index in rows if (node := self.node_at(index)) is not None]

    def visible_action_slots(self, index: QModelIndex) -> dict[int, str]:
        """Which action icons apply to `index`'s row, and each one's slot.

        The first item in a level has no "up" and the last has no "down" —
        there's nowhere for either to go. "First" and "last" are among the
        rows on screen: a row a pending cut is hiding is not a place to move to.
        """
        slots: dict[int, str] = {EDIT_SLOT: "edit", DELETE_SLOT: "delete"}
        if self.neighbor_row(index, -1) is not None:
            slots[UP_SLOT] = "up"
        if self.neighbor_row(index, 1) is not None:
            slots[DOWN_SLOT] = "down"
        return slots

    def neighbor_row(self, index: QModelIndex, delta: int) -> int | None:
        """The nearest visible row above (`delta` -1) or below (+1) `index`.

        Skips rows hidden by a pending cut, which are still in the model (see
        `set_hidden_nodes`), so a move swaps with the neighbor the user can
        see rather than with an invisible one. None at the edge of the level.
        """
        parent = index.parent()
        row = index.row() + delta
        while 0 <= row < self.model().rowCount(parent):
            if not self.isRowHidden(row, parent):
                return row
            row += delta
        return None

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
        key = node.icon or ("section" if node.is_section else "item")
        if key not in self._icon_cache:
            self._icon_cache[key] = at_size(self._source_icon(node), ICON_SIZE)
        return self._icon_cache[key]

    def _source_icon(self, node: MenuNode) -> QIcon:
        """The icon the node names, or the desktop's own folder/file icon."""
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
        """Highlight this level's first row that a pending cut isn't hiding."""
        self.clearSelection()
        root = self.rootIndex()
        for row in range(self.model().rowCount(root)):
            if not self.isRowHidden(row, root):
                self.setCurrentIndex(self.model().index(row, 0, root))
                return

    def descend(self, index: QModelIndex) -> None:
        self.setRootIndex(index)
        self._select_first()
        self.level_changed.emit()

    def ascend(self) -> None:
        came_from = self.rootIndex()
        if not came_from.isValid():
            return  # already at the top level; Left does nothing
        self.setRootIndex(came_from.parent())
        # Land the highlight back on the section we just stepped out of, and
        # drop whatever was multi-selected on the level we're leaving.
        self.clearSelection()
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
            self.launch_requested.emit(node)

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


def _tooltip(node: MenuNode) -> str:
    """What the item points at: a path, the snippet itself, or a child count."""
    if node.is_section:
        count = len(node.children)
        return f"{count} item" if count == 1 else f"{count} items"
    if node.sh is not None:
        lines = node.sh.strip().splitlines()
        if len(lines) > TOOLTIP_LINES:
            lines = lines[:TOOLTIP_LINES] + [f"… {len(lines) - TOOLTIP_LINES} more lines"]
        text = "\n".join(lines)
    else:
        text = node.resolved_file or ""
    if node.launch == LAUNCH_TMUX and node.tmux_session:
        # Which session an item attaches to isn't visible anywhere else, and
        # two items can deliberately share one, so it's worth a line here.
        text += f"\n\ntmux session: {node.tmux_session}"
    return text
