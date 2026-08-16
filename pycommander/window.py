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
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, UI_POINT_SIZE
from .dialogs import FolderNameDialog, ItemEditDialog
from .launcher import TMUX_ATTACH, TMUX_CANCEL, TMUX_RESTART, launch
from .menu import LAUNCH_TMUX, MenuNode, Options, dump_menu, load_menu
from .utils import open_in_editor

NODE_ROLE = Qt.ItemDataRole.UserRole

HINTS = "⏎ launch    e edit menu    q quit"

MENU_POINT_SIZE = UI_POINT_SIZE  # local alias: this file spells it out a lot
ICON_SIZE = 28
BACK_ICON_SIZE = 20  # the header's "go up a level" arrow
BACK_BUTTON_SIZE = 30  # the clickable square that arrow sits in
ROW_PADDING = 10  # px above and below each row's text
TOOLTIP_LINES = 12  # of an inline sh snippet, before the tooltip is truncated

# Right-justified per-row action icons. Slots are numbered from the row's
# right edge, 0 = rightmost, so new icons can join without moving the old
# ones. Left to right on screen: move up, move down, edit, delete.
ACTION_ICON_SIZE = 20
ACTION_ICON_MARGIN = 8  # px around and between icons
DELETE_SLOT = 0
EDIT_SLOT = 1
DOWN_SLOT = 2
UP_SLOT = 3
ACTION_SLOT_COUNT = 4
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


def _back_icon(style: QStyle) -> QIcon:
    """A left-pointing arrow for the header's "go up a level" button."""
    icon = QIcon.fromTheme("go-previous")
    if not icon.isNull():
        return icon
    icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
    if not icon.isNull():
        return icon
    # Same fallback reasoning as `_edit_icon`: draw the glyph ourselves rather
    # than leave an invisible button.
    pixmap = QPixmap(BACK_ICON_SIZE, BACK_ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = painter.font()
    font.setPointSize(BACK_ICON_SIZE - 8)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "←")
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
            "delete": parent.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon),
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
    selection_changed = pyqtSignal()
    launch_failed = pyqtSignal(str)
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
        self._hidden_ids: set[int] = set()  # id()s of the nodes a pending cut hides
        # Set by MainWindow, which owns every dialog this GUI puts up; see
        # launcher.launch's `on_running_session`. Left None (as it is in
        # tests, or any other embedding) tmux mode just attaches, as before.
        self.on_running_session = None
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
        from, which would shift the folder we're standing in.
        """
        model = QStandardItemModel(self)
        self._populate(model.invisibleRootItem(), nodes)
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
        there's nowhere for either to go.
        """
        slots: dict[int, str] = {EDIT_SLOT: "edit", DELETE_SLOT: "delete"}
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
            return  # already at the top level; Left does nothing, as in Commander
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
            error = launch(node, on_running_session=self.on_running_session)
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

        # The header bar: a back arrow, then the breadcrumb. The arrow is the
        # mouse-only equivalent of Left — the app is keyboard-first, but
        # nothing on screen otherwise says how to get back out of a section
        # you clicked your way into.
        self.back_button = QToolButton()
        self.back_button.setIcon(_back_icon(self.style()))
        self.back_button.setIconSize(QSize(BACK_ICON_SIZE, BACK_ICON_SIZE))
        self.back_button.setFixedSize(BACK_BUTTON_SIZE, BACK_BUTTON_SIZE)  # a comfortable target
        self.back_button.setAutoRaise(True)  # flat until hovered
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.setToolTip("Go back (←)")
        # Never take focus: clicking it must leave the arrow keys driving the
        # tree, exactly as if Left had been pressed.
        self.back_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.back_button.clicked.connect(self._go_back)

        self.header = QLabel()
        self.header.setStyleSheet(f"font-weight: bold; font-size: {MENU_POINT_SIZE + 1}pt;")

        self.header_bar = QWidget()
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(10, 10, 14, 10)
        header_layout.setSpacing(8)
        header_layout.addWidget(self.back_button)
        header_layout.addWidget(self.header)
        header_layout.addStretch(1)

        self.tree = MenuTreeView(self)
        self.tree.on_running_session = self._ask_running_session
        self.tree.level_changed.connect(self._update_header)
        self.tree.launch_failed.connect(self._show_launch_error)
        self.tree.edit_requested.connect(self._handle_edit_icon)
        self.tree.delete_requested.connect(self._handle_delete_icon)
        self.tree.move_up_requested.connect(lambda index: self._handle_move(index, -1))
        self.tree.move_down_requested.connect(lambda index: self._handle_move(index, 1))

        # Items the user has cut and not yet pasted. Held in memory only: a cut
        # writes nothing to disk, it just hides the rows until they land
        # somewhere (see `_handle_cut`).
        self.cut_nodes: list[MenuNode] = []

        self.edit_toolbar = QWidget()
        edit_toolbar_layout = QHBoxLayout(self.edit_toolbar)
        edit_toolbar_layout.setContentsMargins(14, 8, 14, 8)
        edit_toolbar_layout.setSpacing(8)
        # Cut/Undo Cut/Paste are shown only when they apply, so the toolbar
        # says what's actually possible right now; `_update_edit_buttons`
        # decides. New Folder/New Item always apply.
        self.cut_button = self._toolbar_button("Cut", self._handle_cut)
        self.undo_cut_button = self._toolbar_button("Undo Cut", self._handle_undo_cut)
        self.paste_button = self._toolbar_button("Paste", self._handle_paste)
        for button in (
            self._toolbar_button("New Folder", self._handle_new_folder),
            self._toolbar_button("New Item", self._handle_new_item),
            self.cut_button,
            self.undo_cut_button,
            self.paste_button,
        ):
            edit_toolbar_layout.addWidget(button)
        edit_toolbar_layout.addStretch(1)
        self.edit_toolbar.setVisible(False)  # only shown while edit mode is on

        self.tree.level_changed.connect(self._update_edit_buttons)
        self.tree.selection_changed.connect(self._update_edit_buttons)

        self.edit_toggle = ToggleSwitch(self)
        self.edit_toggle.toggled.connect(self._handle_edit_toggled)

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
        layout.addWidget(self.header_bar)
        layout.addWidget(self.edit_toolbar)
        layout.addWidget(self.tree, 1)
        layout.addWidget(footer)

        # Shortcuts rather than keyPressEvent: QAbstractItemView swallows plain
        # letter keys (its type-ahead search), so "q" would never reach us here.
        for keys, slot in ((("Esc", "Q"), self.close), (("E",), self.edit_menu)):
            for key in keys:
                QShortcut(QKeySequence(key), self, activated=slot)

        self.tree.set_nodes(nodes)
        self.tree.setFocus()

    def _toolbar_button(self, text: str, slot) -> QPushButton:
        """One button of the edit toolbar, all styled alike."""
        button = QPushButton(text)
        button.setStyleSheet(f"font-size: {MENU_POINT_SIZE - 3}pt; padding: 4px 12px;")
        button.clicked.connect(slot)
        return button

    def _handle_edit_toggled(self, enabled: bool) -> None:
        """The Edit switch was flipped: show or hide everything editing needs.

        Leaving edit mode abandons a pending cut rather than leaving items
        hidden with no visible way to bring them back — nothing is lost, since
        a cut never removed them from the menu file in the first place.
        """
        self.tree.set_edit_mode(enabled)
        self.edit_toolbar.setVisible(enabled)
        if not enabled:
            self._clear_cut()
        self._update_edit_buttons()

    def _update_edit_buttons(self) -> None:
        """Show only the toolbar buttons that apply to the current state.

        Cut and Paste are the two halves of one operation and are never
        offered at the same time: Cut until something has been cut, then Undo
        Cut and Paste until those items land somewhere.
        """
        pending = bool(self.cut_nodes)
        self.undo_cut_button.setVisible(pending)
        self.paste_button.setVisible(pending)
        # Folders can't be cut, so a level's folders alone are not something
        # to offer Cut for.
        cuttable = any(not node.is_section for node in self.tree.selected_nodes())
        self.cut_button.setVisible(not pending and cuttable)

    def _update_header(self) -> None:
        """Show where we are, or nothing at all at the top level.

        The app's name lives in the title bar; inside the window the header
        earns its space only once we've descended into a section, so at the
        top level it disappears entirely rather than leaving a blank strip —
        and with it the back arrow, which has nowhere to go from there.
        """
        crumbs = self.tree.breadcrumb()
        self.header.setText(" / ".join(crumbs))
        self.header_bar.setVisible(bool(crumbs))

    def _go_back(self) -> None:
        """The header's back arrow: go up one level, as Left does."""
        self.tree.ascend()
        self.tree.setFocus()

    def _show_launch_error(self, message: str) -> None:
        QMessageBox.critical(self, f"{APP_NAME} — launch failed", message)

    def _ask_running_session(self, node: MenuNode, session: str, started: str | None) -> str:
        """Attach to `node`'s already-running tmux session, or restart it?

        Attaching is what this mode did unconditionally, and it stays the
        default — but it means the script on disk is never read, so an edited
        script appears to have no effect and the session quietly goes on
        running the version it was started with. Saying when it started is the
        point of the dialog: hours or days ago is the tell.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(f"{APP_NAME} — session already running")
        box.setText(f"The tmux session '{session}' is already running.")
        detail = f"Started {started}.\n\n" if started else ""
        box.setInformativeText(
            f"{detail}"
            "Attach — reconnect to what's running now.\n"
            f"Restart — end that session and run '{node.name}' again from scratch."
        )
        attach = box.addButton("Attach", QMessageBox.ButtonRole.AcceptRole)
        restart = box.addButton("Restart", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(attach)  # the safe one: restarting kills a process
        box.exec()
        clicked = box.clickedButton()
        if clicked is attach:
            return TMUX_ATTACH
        if clicked is restart:
            return TMUX_RESTART
        return TMUX_CANCEL  # includes closing the dialog outright

    def _handle_edit_icon(self, index: QModelIndex) -> None:
        """The row's edit icon was clicked: open the dialog for its kind."""
        node = self.tree.node_at(index)
        if node is None:
            return
        if node.is_section:
            dialog = FolderNameDialog(node.name, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            new_name = dialog.new_name()
            if not new_name or new_name == node.name:
                return
            node.name = new_name
            self._save_and_reload()
            return
        dialog = ItemEditDialog(
            node.name,
            node.file,
            node.sh,
            node.launch,
            node.cwd,
            node.tmux_session,
            self,
            title="Edit Item",
            editor=self.options.resolved_editor(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, file, sh, launch, cwd, tmux_session = dialog.results()
        if not name:
            return
        node.name = name
        node.file = file
        node.sh = sh
        node.launch = launch
        node.cwd = cwd
        node.tmux_session = tmux_session
        self._save_and_reload()

    def _handle_delete_icon(self, index: QModelIndex) -> None:
        """The row's delete icon was clicked; confirm, then remove the item."""
        node = self.tree.node_at(index)
        if node is None:
            return
        siblings = self._sibling_list(index)
        if siblings is self.nodes and len(siblings) == 1:
            # menu.py requires the top-level menu to keep at least one item;
            # a section, unlike the top level, is allowed to end up empty.
            QMessageBox.warning(
                self, f"{APP_NAME} — cannot delete", "The menu can't be left with no items at all."
            )
            return
        detail = (
            f" This deletes {len(node.children)} item(s) inside it too."
            if node.is_section and node.children
            else ""
        )
        reply = QMessageBox.question(
            self,
            "Delete",
            f'Delete "{node.name}"?{detail}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del siblings[index.row()]
        self._save_and_reload()

    def _handle_new_folder(self) -> None:
        """The toolbar's "New Folder" button was clicked.

        The new folder is appended to whichever level is currently on
        screen — `self.nodes` at the top, or the section we've drilled into
        — starting out empty; the user can descend into it with Right, but
        there's no way to populate it until "New Item" exists.
        """
        dialog = FolderNameDialog("", self, title="New Folder Name")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.new_name()
        if not name:
            return
        self._current_level_nodes().append(MenuNode(name=name))
        self._save_and_reload(select_name=name)

    def _handle_new_item(self) -> None:
        """The toolbar's "New Item" button was clicked.

        Same placement rule as "New Folder": the new item is appended to
        whichever level is currently on screen.
        """
        dialog = ItemEditDialog(parent=self, title="Create Item", editor=self.options.resolved_editor())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, file, sh, launch, cwd, tmux_session = dialog.results()
        if not name:
            return
        self._current_level_nodes().append(
            MenuNode(
                name=name, file=file, sh=sh, launch=launch, cwd=cwd, tmux_session=tmux_session
            )
        )
        self._save_and_reload(select_name=name)

    def _handle_cut(self) -> None:
        """The toolbar's "Cut" button was clicked.

        Whatever is selected *right now* becomes the cut set, replacing any
        earlier one — cutting is a reset, not something that accumulates as
        the user walks around the tree. Nothing is written to disk and nothing
        leaves the in-memory tree yet; the items are only hidden, so a cut
        that's never pasted costs nothing.
        """
        selected = self.tree.selected_nodes()
        folders = [node for node in selected if node.is_section]
        if folders:
            names = ", ".join(f'"{node.name}"' for node in folders)
            QMessageBox.warning(
                self,
                f"{APP_NAME} — cannot cut",
                f"Folders can't be cut and pasted — only items can.\n\n"
                f"Deselect {names} and try again.",
            )
            return
        if not selected:
            return
        self.cut_nodes = selected
        self.tree.set_hidden_nodes(self.cut_nodes)
        self._update_edit_buttons()

    def _handle_undo_cut(self) -> None:
        """The toolbar's "Undo Cut" button was clicked: unhide the cut items.

        There is nothing else to undo — the cut items never moved.
        """
        self._clear_cut()
        self._update_edit_buttons()

    def _handle_paste(self) -> None:
        """The toolbar's "Paste" button was clicked.

        The cut items are appended to whichever level is currently on screen —
        the same placement rule New Folder/New Item use — and *this* is the
        step that makes the move permanent, since it's the first one to write
        the file.
        """
        if not self.cut_nodes:
            return
        pasted = self.cut_nodes
        target = self._current_level_nodes()
        for node in pasted:
            _detach_node(self.nodes, node)  # remove from wherever it was cut from
        target.extend(pasted)  # `target` survives the removals: same list object
        self._clear_cut()
        self._save_and_reload(select_name=pasted[0].name)

    def _clear_cut(self) -> None:
        """Forget any pending cut and put its rows back on screen."""
        if not self.cut_nodes:
            return
        self.cut_nodes = []
        self.tree.set_hidden_nodes([])

    def _current_level_nodes(self) -> list[MenuNode]:
        """The MenuNode list for the level currently shown in the tree.

        `self.nodes` at the top level, or the section's `children` once
        we've drilled in — found by walking `self.nodes` down the same
        row-path `current_path()` describes.
        """
        nodes = self.nodes
        for row in self.tree.current_path():
            nodes = nodes[row].children
        return nodes

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

    def _save_and_reload(self, select_name: str | None = None) -> None:
        """Write `self.nodes`/`options` out, then reload from disk.

        Rather than patch the tree view's model in place, this takes the
        same one-way trip through `load_menu` that startup does — simpler
        to get right, and it guarantees the GUI matches what's actually on
        disk. The user's current folder is preserved across the rebuild, and
        so is the highlighted row — `select_name`, when given, picks out a
        row that wasn't already highlighted (e.g. one just created); left
        unset, whatever was highlighted before stays highlighted.

        A pending cut can't survive this: the reload replaces every MenuNode
        object, so the cut list would be pointing at nodes that are no longer
        in the tree. It's dropped instead — the cut items reappear where they
        were, which is where they still are on disk.
        """
        self._clear_cut()
        path = self.tree.breadcrumb()
        if select_name is None:
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


def _detach_node(nodes: list[MenuNode], target: MenuNode) -> bool:
    """Remove `target` from `nodes` or any section under it. True if found.

    Identity, not equality: MenuNode is a dataclass, so two items that happen
    to carry the same fields compare equal and `list.remove` would drop the
    wrong one.
    """
    for i, node in enumerate(nodes):
        if node is target:
            del nodes[i]
            return True
        if node.is_section and _detach_node(node.children, target):
            return True
    return False


def _tooltip(node: MenuNode) -> str:
    """What the item points at: a path, the snippet itself, or a child count."""
    if node.is_section:
        return f"{len(node.children)} items"
    if node.sh is not None:
        lines = node.sh.strip().splitlines()
        if len(lines) > TOOLTIP_LINES:
            lines = lines[:TOOLTIP_LINES] + [f"… {len(lines) - TOOLTIP_LINES} more lines"]
        text = "\n".join(lines)
    else:
        text = node.resolved_file
    if node.launch == LAUNCH_TMUX and node.tmux_session:
        # Which session an item attaches to isn't visible anywhere else, and
        # two items can deliberately share one, so it's worth a line here.
        text += f"\n\ntmux session: {node.tmux_session}"
    return text


def format_errors(menu_path: str, errors: list[str]) -> str:
    lines = "\n".join(f"  • {e}" for e in errors)
    return f"{menu_path} has {len(errors)} problem(s):\n\n{lines}"
