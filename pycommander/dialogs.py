"""Editing dialogs opened from the tree's per-row action icons.

One dialog class per editable thing: a folder's name (`FolderNameDialog`,
shared between renaming an existing folder and naming a brand new one), and
a launchable item's name/file-or-sh/cwd/launch mode (`ItemEditDialog`, same
reuse between edit and create). Item reordering has no dialog of its own —
it's driven straight from the row's up/down icons.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import (
    QColor,
    QFontDatabase,
    QFontMetrics,
    QPalette,
    QRegularExpressionValidator,
)
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import UI_POINT_SIZE
from .menu import (
    DEFAULT_LAUNCH,
    LAUNCH_DETACHED,
    LAUNCH_HOLD,
    LAUNCH_MODES,
    LAUNCH_TERMINAL,
    LAUNCH_TMUX,
)
from .utils import open_in_editor

# A plain QDialog's outer edge is easy to lose against the desktop behind it,
# so the real content sits inside a bordered QFrame instead — a QDialog won't
# reliably paint a stylesheet border of its own, but a QFrame always will.
BORDER_STYLE = "#dialogFrame { border: 1px solid #a0a0a0; border-radius: 6px; }"
LABEL_STYLE = f"font-size: {UI_POINT_SIZE}pt;"
BUTTON_STYLE = f"QPushButton {{ font-size: {UI_POINT_SIZE}pt; padding: 8px 20px; }}"

# Friendly text for the launch-mode combobox; the underlying values (stored
# as each item's data) are the same strings menu.py reads and writes.
LAUNCH_LABELS = {
    LAUNCH_DETACHED: "Detached (no window)",
    LAUNCH_TERMINAL: "Terminal (terminal auto-closes)",
    LAUNCH_HOLD: "Hold (terminal stays open)",
    LAUNCH_TMUX: "Tmux (session keeps running)",
}

# Same restriction launcher.py enforces on a hand-edited menu file; here it
# stops the offending characters being typed in the first place.
TMUX_SESSION_PATTERN = r"[A-Za-z0-9_-]*"

# The sh editor is sized to comfortably show a script this big without
# scrolling; longer scripts just scroll normally.
SH_EDITOR_COLUMNS = 80
SH_EDITOR_ROWS = 10

# AdjustToContents sizes the closed combo box to its current item's text, but
# the dropdown popup's own item padding isn't accounted for by that, so the
# longest label ends up elided with "…" once the popup opens. This is added
# on top of the longest label's measured width to give the popup room too.
LAUNCH_COMBO_EXTRA_WIDTH = 150


def _field_background() -> str:
    """A background a shade lighter than the theme's default input color.

    Computed from the live application palette (rather than a fixed hex)
    so it lightens relative to whatever the desktop theme's own input
    background is, instead of assuming a light or a dark theme. Queried
    lazily — at dialog-build time, not import time — since no theme is
    attached to the palette until QApplication exists.
    """
    base = QApplication.palette().color(QPalette.ColorRole.Base)
    return base.lighter(130).name()


def _field_border() -> str:
    """A light-gray border, guaranteed lighter than the field's own
    background so it actually reads as an outline instead of vanishing into
    it. Setting any QSS on a widget (as `_field_background` does) opts it
    out of the style's native border too, so this is drawn explicitly
    rather than relying on a native on/off switch.
    """
    return QColor(_field_background()).lighter(140).name()


def _field_style() -> str:
    """Shared padding/font styling for single-line inputs and the combobox,
    plus the lightened background and border from `_field_background` and
    `_field_border`."""
    return (
        f"padding: 8px; font-size: {UI_POINT_SIZE}pt;"
        f" background-color: {_field_background()}; border: 1px solid {_field_border()};"
    )


class FolderNameDialog(QDialog):
    """A single text field for naming a section ('folder:') entry.

    Reused for both renaming an existing folder and naming a new one — the
    `title` decides which, since the field itself is identical either way.
    """

    def __init__(self, current_name: str, parent: QWidget | None = None, title: str = "Rename") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(440, 220)

        self._name_edit = QLineEdit(current_name)
        self._name_edit.setStyleSheet(_field_style())
        self._name_edit.selectAll()

        label = QLabel("Folder name:")
        label.setStyleSheet(LABEL_STYLE)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setStyleSheet(BUTTON_STYLE)
        self._save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        frame = QFrame(self)
        frame.setObjectName("dialogFrame")
        frame.setStyleSheet(BORDER_STYLE)

        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(24, 24, 24, 24)
        frame_layout.setSpacing(14)
        frame_layout.addWidget(label)
        frame_layout.addWidget(self._name_edit)
        frame_layout.addStretch(1)
        frame_layout.addWidget(buttons)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.addWidget(frame)

        self._name_edit.textChanged.connect(self._validate)
        self._validate()
        self._name_edit.setFocus()

    def _validate(self) -> None:
        # A blank name would leave the item unlabeled, so Save stays disabled.
        self._save_button.setEnabled(bool(self._name_edit.text().strip()))

    def new_name(self) -> str:
        return self._name_edit.text().strip()


class ItemEditDialog(QDialog):
    """Name, file-or-sh, working directory, and launch mode for a launchable
    ('name:') entry.

    Reused for editing an existing item and creating a new one — same as
    `FolderNameDialog`, the `title` decides which. A radio pair picks whether
    the item runs a `file:` on disk or an inline `sh:` snippet; only the
    matching editor for that choice is shown, swapped via a QStackedWidget.
    The working directory (`cwd:`) is required and applies to both kinds, so
    it sits below the stacked file/sh editor rather than inside either page.
    """

    def __init__(
        self,
        name: str = "",
        file: str | None = None,
        sh: str | None = None,
        launch: str = DEFAULT_LAUNCH,
        cwd: str | None = None,
        tmux_session: str | None = None,
        parent: QWidget | None = None,
        title: str = "Edit Item",
        editor: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(680, 700)
        self._editor = editor

        name_label = QLabel("Name:")
        name_label.setStyleSheet(LABEL_STYLE)
        self._name_edit = QLineEdit(name)
        self._name_edit.setStyleSheet(_field_style())

        is_sh = sh is not None
        self._file_radio = QRadioButton("File")
        self._sh_radio = QRadioButton("Bash script")
        for radio in (self._file_radio, self._sh_radio):
            radio.setStyleSheet(LABEL_STYLE)
        self._type_group = QButtonGroup(self)
        self._type_group.addButton(self._file_radio)
        self._type_group.addButton(self._sh_radio)
        self._file_radio.setChecked(not is_sh)
        self._sh_radio.setChecked(is_sh)

        type_row = QHBoxLayout()
        type_row.addWidget(self._file_radio)
        type_row.addWidget(self._sh_radio)
        type_row.addStretch(1)

        self._file_edit = QLineEdit(file or "")
        self._file_edit.setStyleSheet(_field_style())
        pick_button = QPushButton("Pick File…")
        pick_button.setStyleSheet(BUTTON_STYLE)
        pick_button.clicked.connect(self._pick_file)
        # Opens the path currently in _file_edit in the configured editor —
        # the same open_in_editor() used for the "e" (edit menu.yaml) shortcut
        # — so a script can be edited without leaving PyCommander.
        self._edit_file_button = QPushButton("Edit")
        self._edit_file_button.setStyleSheet(BUTTON_STYLE)
        self._edit_file_button.clicked.connect(self._edit_file)

        file_buttons_row = QHBoxLayout()
        file_buttons_row.addWidget(pick_button)
        file_buttons_row.addWidget(self._edit_file_button)
        file_buttons_row.addStretch(1)

        file_page = QWidget()
        file_page_layout = QVBoxLayout(file_page)
        file_page_layout.setContentsMargins(0, 0, 0, 0)
        file_page_layout.setSpacing(10)
        file_page_layout.addWidget(self._file_edit)
        file_page_layout.addLayout(file_buttons_row)
        file_page_layout.addStretch(1)

        # A fixed-width font, and a size big enough to show a real script
        # without scrolling — no syntax highlighting, just a plain editor.
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(UI_POINT_SIZE)
        self._sh_edit = QPlainTextEdit(sh or "")
        self._sh_edit.setFont(mono_font)
        self._sh_edit.setStyleSheet(
            f"background-color: {_field_background()}; border: 1px solid {_field_border()};"
        )
        self._sh_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        metrics = QFontMetrics(mono_font)
        self._sh_edit.setMinimumSize(
            metrics.horizontalAdvance("M") * SH_EDITOR_COLUMNS + 24,
            metrics.lineSpacing() * SH_EDITOR_ROWS + 24,
        )

        sh_page = QWidget()
        sh_page_layout = QVBoxLayout(sh_page)
        sh_page_layout.setContentsMargins(0, 0, 0, 0)
        sh_page_layout.addWidget(self._sh_edit)

        self._stack = QStackedWidget()
        self._stack.addWidget(file_page)
        self._stack.addWidget(sh_page)
        self._stack.setCurrentIndex(1 if is_sh else 0)
        self._file_radio.toggled.connect(
            lambda checked: checked and self._stack.setCurrentIndex(0)
        )
        self._sh_radio.toggled.connect(lambda checked: checked and self._stack.setCurrentIndex(1))

        # Required on every launchable item (see menu.py's resolved_cwd) — the
        # working directory the script or sh: snippet runs from. Shown below
        # the file/sh picker regardless of which of those is selected, since
        # both need one.
        cwd_label = QLabel("Working directory:")
        cwd_label.setStyleSheet(LABEL_STYLE)
        self._cwd_edit = QLineEdit(cwd or "")
        self._cwd_edit.setStyleSheet(_field_style())
        pick_cwd_button = QPushButton("Pick Folder…")
        pick_cwd_button.setStyleSheet(BUTTON_STYLE)
        pick_cwd_button.clicked.connect(self._pick_cwd)

        cwd_button_row = QHBoxLayout()
        cwd_button_row.addWidget(pick_cwd_button)
        cwd_button_row.addStretch(1)

        launch_label = QLabel("Launch:")
        launch_label.setStyleSheet(LABEL_STYLE)
        self._launch_combo = QComboBox()
        self._launch_combo.setStyleSheet(_field_style())
        for mode in LAUNCH_MODES:
            self._launch_combo.addItem(LAUNCH_LABELS[mode], mode)
        launch_index = self._launch_combo.findData(launch)
        self._launch_combo.setCurrentIndex(launch_index if launch_index >= 0 else 0)
        # Size to the longest label instead of stretching across the dialog.
        self._launch_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._launch_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        # AdjustToContents alone leaves the dropdown popup too narrow for its
        # own longest entry (see LAUNCH_COMBO_EXTRA_WIDTH); floor the width.
        metrics = QFontMetrics(self._launch_combo.font())
        longest_label = max(LAUNCH_LABELS.values(), key=len)
        self._launch_combo.setMinimumWidth(
            metrics.horizontalAdvance(longest_label) + LAUNCH_COMBO_EXTRA_WIDTH
        )
        launch_row = QHBoxLayout()
        launch_row.addWidget(self._launch_combo)
        launch_row.addStretch(1)

        # Only meaningful under the tmux launch mode, so the label and field
        # are shown only while that mode is picked (_update_tmux_visibility) —
        # the same "the control decides what's on screen" idea as the file/sh
        # radio pair driving the stack above, just a plain show/hide since
        # there's one field rather than two whole pages.
        self._tmux_label = QLabel("Tmux session name:")
        self._tmux_label.setStyleSheet(LABEL_STYLE)
        self._tmux_edit = QLineEdit(tmux_session or "")
        self._tmux_edit.setStyleSheet(_field_style())
        self._tmux_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(TMUX_SESSION_PATTERN), self)
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setStyleSheet(BUTTON_STYLE)
        self._save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        frame = QFrame(self)
        frame.setObjectName("dialogFrame")
        frame.setStyleSheet(BORDER_STYLE)

        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(24, 24, 24, 24)
        frame_layout.setSpacing(14)
        frame_layout.addWidget(name_label)
        frame_layout.addWidget(self._name_edit)
        frame_layout.addLayout(type_row)
        frame_layout.addWidget(self._stack, 1)
        frame_layout.addWidget(cwd_label)
        frame_layout.addWidget(self._cwd_edit)
        frame_layout.addLayout(cwd_button_row)
        frame_layout.addWidget(launch_label)
        frame_layout.addLayout(launch_row)
        frame_layout.addWidget(self._tmux_label)
        frame_layout.addWidget(self._tmux_edit)
        frame_layout.addWidget(buttons)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.addWidget(frame)

        self._name_edit.textChanged.connect(self._validate)
        self._file_edit.textChanged.connect(self._validate)
        self._sh_edit.textChanged.connect(self._validate)
        self._cwd_edit.textChanged.connect(self._validate)
        self._file_radio.toggled.connect(self._validate)
        self._tmux_edit.textChanged.connect(self._validate)
        self._launch_combo.currentIndexChanged.connect(self._update_tmux_visibility)
        self._launch_combo.currentIndexChanged.connect(self._validate)
        self._validate()
        self._update_tmux_visibility()  # so a freshly opened dialog starts right
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _update_tmux_visibility(self) -> None:
        is_tmux = self._launch_combo.currentData() == LAUNCH_TMUX
        self._tmux_label.setVisible(is_tmux)
        self._tmux_edit.setVisible(is_tmux)

    def _pick_file(self) -> None:
        # `file:` is often just a bare name once a prior pick has split it
        # (below), so it's not a usable start location on its own; the
        # folder currently in `cwd:` is a better guess of where to reopen.
        file_text = self._file_edit.text().strip()
        if file_text and os.path.isabs(os.path.expanduser(file_text)):
            start = file_text
        else:
            start = self._cwd_edit.text().strip() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select script file", start)
        if not path:
            return
        # Split the picked path: the file name alone goes in `file:`, and its
        # containing folder becomes `cwd:` — that's what a user picking a
        # script almost always wants, so this overwrites whatever was already
        # in the working-directory field rather than leaving it alone.
        directory, name = os.path.split(path)
        self._file_edit.setText(name)
        self._cwd_edit.setText(directory)

    def _pick_cwd(self) -> None:
        start = self._cwd_edit.text().strip() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Select working directory", start)
        if path:
            self._cwd_edit.setText(path)

    def _edit_file(self) -> None:
        path = self._file_edit.text().strip()
        if not path:
            return
        # Resolved the same way menu.py's `resolved_file` does it, since what's
        # in the field is usually a bare file name that "Pick File…" split off
        # into `file:` + `cwd:` — on its own it names nothing on disk, and the
        # editor would be pointed at a directory-less path.
        resolved = os.path.expanduser(os.path.expandvars(path))
        if not os.path.isabs(resolved):
            cwd = self._cwd_edit.text().strip()
            if cwd:
                resolved = os.path.join(os.path.expanduser(os.path.expandvars(cwd)), resolved)
        error = open_in_editor(resolved, self._editor)
        if error:
            QMessageBox.critical(self, "Cannot edit file", error)

    def _validate(self) -> None:
        # A blank name, a blank file/sh for whichever type is selected, or a
        # blank cwd would leave the item unusable, so Save stays disabled. A
        # tmux item needs a session name for the same reason — but only while
        # that mode is the one selected.
        name_ok = bool(self._name_edit.text().strip())
        file_ok = bool(self._file_edit.text().strip())
        content_ok = bool(self._sh_edit.toPlainText().strip()) if self._sh_radio.isChecked() else file_ok
        cwd_ok = bool(self._cwd_edit.text().strip())
        tmux_ok = (
            bool(self._tmux_edit.text().strip())
            if self._launch_combo.currentData() == LAUNCH_TMUX
            else True
        )
        self._save_button.setEnabled(name_ok and content_ok and cwd_ok and tmux_ok)
        # Edit only makes sense once there's a path to open.
        self._edit_file_button.setEnabled(file_ok)

    def results(self) -> tuple[str, str | None, str | None, str, str, str | None]:
        """The fields as `(name, file, sh, launch, cwd, tmux_session)`, for a MenuNode.

        The session name comes back whatever the launch mode is, so switching
        the mode away from tmux and back doesn't quietly discard what was
        typed; only whether it's *required* depends on the mode (`_validate`).
        """
        name = self._name_edit.text().strip()
        launch = self._launch_combo.currentData()
        cwd = self._cwd_edit.text().strip()
        tmux_session = self._tmux_edit.text().strip() or None
        if self._sh_radio.isChecked():
            return name, None, self._sh_edit.toPlainText(), launch, cwd, tmux_session
        return name, self._file_edit.text().strip(), None, launch, cwd, tmux_session
