"""The GUI: a real QTreeView, but showing exactly one level at a time.

The whole menu tree lives in a QStandardItemModel. Drilling down is
`setRootIndex(child)` rather than expanding, so the view renders one level
at a time — the navigation model of the original curses Commander — while
still being a native tree with per-item icons.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QModelIndex, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QMessageBox,
    QStyle,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME
from .launcher import launch
from .menu import MenuError, MenuNode, load_menu

NODE_ROLE = Qt.ItemDataRole.UserRole

HINTS = "↑↓ move    → open    ← back    ⏎ launch    F5 reload    q quit"


class MenuTreeView(QTreeView):
    """One-level-at-a-time tree driven entirely by the arrow keys."""

    level_changed = pyqtSignal()
    launch_failed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)  # no expand arrows: levels never expand
        self.setItemsExpandable(False)
        self.setExpandsOnDoubleClick(False)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(22, 22))
        self.setIndentation(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.doubleClicked.connect(self._activate)

    # -- model ---------------------------------------------------------------

    def set_nodes(self, nodes: list[MenuNode]) -> None:
        """Replace the menu, returning the view to the top level."""
        model = QStandardItemModel(self)
        self._populate(model.invisibleRootItem(), nodes)
        previous = self.model()
        self.setModel(model)
        if previous is not None:
            previous.deleteLater()  # setModel doesn't own it; reloads would pile up
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
            item.setToolTip(node.resolved_file or f"{len(node.children)} items")
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

    def current_path(self) -> list[str]:
        """Breadcrumb plus the highlighted item — enough to restore a reload."""
        path = self.breadcrumb()
        current = self.currentIndex()
        if current.isValid():
            path.append(current.data(Qt.ItemDataRole.DisplayRole))
        return path

    def restore_path(self, path: list[str]) -> None:
        """Best-effort: descend as far along `path` as the new menu still allows.

        `path` is a breadcrumb followed by the highlighted item's name, as
        returned by current_path(). Anything the reloaded menu no longer has
        just stops the walk early.
        """
        if not path:
            return
        model = self.model()
        root = QModelIndex()
        for name in path[:-1]:
            child = self._find_child(root, name)
            if not child.isValid() or not model.hasChildren(child):
                break
            root = child
        self.setRootIndex(root)
        target = self._find_child(root, path[-1])
        if target.isValid():
            self.setCurrentIndex(target)
        else:
            self._select_first()
        self.level_changed.emit()

    def _find_child(self, parent: QModelIndex, name: str) -> QModelIndex:
        model = self.model()
        for row in range(model.rowCount(parent)):
            child = model.index(row, 0, parent)
            if child.data(Qt.ItemDataRole.DisplayRole) == name:
                return child
        return QModelIndex()

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
    def __init__(self, menu_path: str, nodes: list[MenuNode]) -> None:
        super().__init__()
        self.menu_path = menu_path

        self.setWindowTitle(APP_NAME)
        self.resize(560, 640)

        self.header = QLabel()
        self.header.setStyleSheet("font-weight: bold; padding: 6px 8px;")

        self.tree = MenuTreeView(self)
        self.tree.level_changed.connect(self._update_header)
        self.tree.launch_failed.connect(self._show_launch_error)

        footer = QLabel(HINTS)
        footer.setStyleSheet("padding: 6px 8px;")
        footer.setEnabled(False)  # renders in the theme's disabled (dim) color

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.tree, 1)
        layout.addWidget(footer)

        # Shortcuts rather than keyPressEvent: QAbstractItemView swallows plain
        # letter keys (its type-ahead search), so "q" would never reach us here.
        for keys, slot in (
            (("Esc", "Q"), self.close),
            (("F5", "Ctrl+R"), self.reload),
        ):
            for key in keys:
                QShortcut(QKeySequence(key), self, activated=slot)

        self.tree.set_nodes(nodes)
        self.tree.setFocus()

    def _update_header(self) -> None:
        crumbs = self.tree.breadcrumb()
        self.header.setText(" — ".join([APP_NAME, *crumbs]) if crumbs else APP_NAME)

    def _show_launch_error(self, message: str) -> None:
        QMessageBox.critical(self, f"{APP_NAME} — launch failed", message)

    def reload(self) -> None:
        """Re-read the menu file, keeping the old menu if the new one is broken."""
        try:
            nodes, errors = load_menu(self.menu_path)
        except MenuError as exc:
            QMessageBox.critical(self, f"{APP_NAME} — reload failed", str(exc))
            return
        if errors:
            QMessageBox.critical(
                self,
                f"{APP_NAME} — reload failed",
                format_errors(self.menu_path, errors) + "\n\nThe previous menu is still loaded.",
            )
            return
        path = self.tree.current_path()
        self.tree.set_nodes(nodes)
        self.tree.restore_path(path)
        self.tree.setFocus()


def format_errors(menu_path: str, errors: list[str]) -> str:
    lines = "\n".join(f"  • {e}" for e in errors)
    return f"{menu_path} has {len(errors)} problem(s):\n\n{lines}"
