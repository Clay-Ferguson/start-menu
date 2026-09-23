"""The main window: header, the menu, the edit toolbar and the footer.

`MainWindow` owns everything that changes the menu or talks to the user in a
dialog. The menu view itself is `tree.MenuTreeView`, which only reports what
was asked for; this module acts on it — launching, editing, cut/paste — and
saves every change straight back to the menu file.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QModelIndex, QSize, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from windowchrome import ToggleSwitch

from . import APP_NAME, UI_POINT_SIZE
from .folder_dialog import FolderNameDialog
from .icons import at_size, back_icon
from .item_dialog import ItemEditDialog
from .launcher import TMUX_ATTACH, TMUX_CANCEL, TMUX_RESTART, launch, open_in_editor
from .menu import (
    MenuError,
    MenuNode,
    Options,
    detach_node,
    dump_menu,
    format_errors,
    load_menu,
    nodes_at,
)
from .style import HIGHLIGHT_BG
from .tree import MenuTreeView

HINTS = "⏎ launch    e edit menu    q quit"

BACK_ICON_SIZE = 24  # the header's "go up a level" arrow
BACK_BUTTON_SIZE = 36  # the clickable square that arrow sits in


class MainWindow(QWidget):
    def __init__(self, menu_path: str, nodes: list[MenuNode], options: Options) -> None:
        super().__init__()
        self.menu_path = menu_path
        self.nodes = nodes
        self.options = options
        # When the file on disk was last known to match `self.nodes`, so a save
        # can tell whether something else — the "e" editor, most likely — has
        # rewritten it since. See `_save_and_reload`.
        self._menu_mtime = _mtime(menu_path)

        self.setWindowTitle(APP_NAME)
        self.resize(560, 640)

        # The header bar: a back arrow, then the breadcrumb. The arrow is the
        # mouse-only equivalent of Left — the app is keyboard-first, but
        # nothing on screen otherwise says how to get back out of a section
        # you clicked your way into.
        self.back_button = QToolButton()
        self.back_button.setIcon(at_size(back_icon(self.style(), BACK_ICON_SIZE), BACK_ICON_SIZE))
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
        self.header.setStyleSheet(f"font-weight: bold; font-size: {UI_POINT_SIZE + 1}pt;")

        self.header_bar = QWidget()
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(10, 10, 14, 10)
        header_layout.setSpacing(8)
        header_layout.addWidget(self.back_button)
        header_layout.addWidget(self.header)
        header_layout.addStretch(1)

        self.tree = MenuTreeView(self)
        self.tree.level_changed.connect(self._update_header)
        self.tree.launch_requested.connect(self._launch)
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

        self.edit_toggle = ToggleSwitch(self, on_color=HIGHLIGHT_BG)
        self.edit_toggle.toggled.connect(self._handle_edit_toggled)

        edit_label = QLabel("Edit")
        edit_label.setStyleSheet(f"font-size: {UI_POINT_SIZE - 3}pt;")

        hints = QLabel(HINTS)
        hints.setStyleSheet(f"font-size: {UI_POINT_SIZE - 3}pt;")
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
                QShortcut(QKeySequence(key), self).activated.connect(slot)

        self.tree.set_nodes(nodes)
        self.tree.setFocus()

    def _toolbar_button(self, text: str, slot) -> QPushButton:
        """One button of the edit toolbar, all styled alike."""
        button = QPushButton(text)
        button.setStyleSheet(f"font-size: {UI_POINT_SIZE - 3}pt; padding: 4px 12px;")
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

    def _launch(self, node: MenuNode) -> None:
        """Run a script the tree asked for, and say so if it couldn't be run."""
        error = launch(node, on_running_session=self._ask_running_session)
        if error:
            QMessageBox.critical(self, f"{APP_NAME} — launch failed", error)

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
            node, self, title="Edit Item", editor=self.options.resolved_editor()
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        edited = dialog.edited_item()
        if not edited.name:
            return
        self._sibling_list(index)[index.row()] = edited
        # By name, since the edit may have renamed the very row to highlight.
        self._save_and_reload(select_name=edited.name)

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
        dialog = ItemEditDialog(
            parent=self, title="Create Item", editor=self.options.resolved_editor()
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        created = dialog.edited_item()
        if not created.name:
            return
        self._current_level_nodes().append(created)
        self._save_and_reload(select_name=created.name)

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
            detach_node(self.nodes, node)  # remove from wherever it was cut from
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
        return nodes_at(self.nodes, self.tree.current_path())

    def _handle_move(self, index: QModelIndex, delta: int) -> None:
        """The row's move up/down icon was clicked; `delta` is -1 or +1."""
        siblings = self._sibling_list(index)
        pos = index.row()
        new_pos = self.tree.neighbor_row(index, delta)
        if new_pos is None:
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
        return nodes_at(self.nodes, rows)

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

        Every caller has already changed `self.nodes` by the time this runs,
        while the view still shows the old rows. So no path out of here may
        leave the two disagreeing: the view maps rows to nodes by row number,
        and a mismatch would aim the next edit at the wrong item. Whatever
        goes wrong, the tree is rebuilt — from disk when the edit was not
        written, and from `self.nodes` when the file won't load back.
        """
        self._clear_cut()
        path = self.tree.breadcrumb()
        if select_name is None:
            select_name = self.tree.current_selection_name()

        # The file was changed behind our back (the "e" editor, usually).
        # Saving now would rewrite it from the tree loaded before that edit
        # and silently throw the edit away, so the file wins instead: this
        # change is dropped and the window picks up what's on disk.
        if _mtime(self.menu_path) != self._menu_mtime:
            QMessageBox.warning(
                self,
                f"{APP_NAME} — menu file changed",
                f"{self.menu_path} was changed outside {APP_NAME}.\n\n"
                "Your last change was not saved, so as not to overwrite that "
                "edit. The menu has been reloaded from the file; make the "
                "change again if you still want it.",
            )
            if not self._reload_from_disk(path, select_name):
                self.tree.set_nodes(self.nodes, restore_path=path, select_name=select_name)
            return

        try:
            dump_menu(self.menu_path, self.nodes, self.options)
        except OSError as exc:
            QMessageBox.critical(
                self,
                f"{APP_NAME} — cannot save menu",
                f"Could not write {self.menu_path}:\n\n{exc}",
            )
            # The write is atomic, so the file still holds the menu as it was
            # before this edit; going back to it undoes the in-memory change.
            if not self._reload_from_disk(path, select_name):
                self.tree.set_nodes(self.nodes, restore_path=path, select_name=select_name)
            return

        self._menu_mtime = _mtime(self.menu_path)
        if not self._reload_from_disk(path, select_name):
            # What we wrote doesn't load back. The file and `self.nodes` agree
            # with each other, so show that rather than the stale rows. (The
            # same last resort as above, where the file couldn't be read.)
            self.tree.set_nodes(self.nodes, restore_path=path, select_name=select_name)

    def _reload_from_disk(self, path: list[str], select_name: str | None) -> bool:
        """Replace the tree with what `menu_path` holds now. False if it can't.

        Reports its own failures. On one, `self.nodes` and the view are left
        exactly as they were, for the caller to decide what to show.
        """
        try:
            nodes, options, errors = load_menu(self.menu_path)
        except MenuError as exc:
            QMessageBox.critical(self, f"{APP_NAME} — cannot reload menu", str(exc))
            return False
        if errors:
            QMessageBox.critical(
                self, f"{APP_NAME} — cannot reload menu", format_errors(self.menu_path, errors)
            )
            return False
        self.nodes = nodes
        self.options = options
        self._menu_mtime = _mtime(self.menu_path)
        self.tree.set_nodes(nodes, restore_path=path, select_name=select_name)
        return True

    def edit_menu(self) -> None:
        """Open the menu file itself in the configured editor.

        The window stays open, but nothing re-reads the file — edits take
        effect the next time Start Menu starts.
        """
        error = open_in_editor(self.menu_path, self.options.resolved_editor())
        if error:
            QMessageBox.critical(self, f"{APP_NAME} — cannot edit menu", error)


def _mtime(path: str) -> int | None:
    """`path`'s modification time in ns, or None if it can't be read."""
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None
