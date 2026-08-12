"""Editing dialogs opened from the tree's per-row action icons.

One dialog class per editable thing: a folder's name (`FolderNameDialog`,
shared between renaming an existing folder and naming a brand new one), and
a launchable item's name/file-or-sh/launch mode (`ItemEditDialog`, same
reuse between edit and create). Item reordering has no dialog of its own —
it's driven straight from the row's up/down icons.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFontDatabase, QFontMetrics, QPalette
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
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import UI_POINT_SIZE
from .menu import DEFAULT_LAUNCH, LAUNCH_DETACHED, LAUNCH_HOLD, LAUNCH_MODES, LAUNCH_TERMINAL

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
}

# The sh editor is sized to comfortably show a script this big without
# scrolling; longer scripts just scroll normally.
SH_EDITOR_COLUMNS = 80
SH_EDITOR_ROWS = 10


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
    """Name, file-or-sh, and launch mode for a launchable ('name:') entry.

    Reused for editing an existing item and creating a new one — same as
    `FolderNameDialog`, the `title` decides which. A radio pair picks whether
    the item runs a `file:` on disk or an inline `sh:` snippet; only the
    matching editor for that choice is shown, swapped via a QStackedWidget.
    """

    def __init__(
        self,
        name: str = "",
        file: str | None = None,
        sh: str | None = None,
        launch: str = DEFAULT_LAUNCH,
        parent: QWidget | None = None,
        title: str = "Edit Item",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(680, 640)

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

        file_page = QWidget()
        file_page_layout = QVBoxLayout(file_page)
        file_page_layout.setContentsMargins(0, 0, 0, 0)
        file_page_layout.setSpacing(10)
        file_page_layout.addWidget(self._file_edit)
        file_page_layout.addWidget(pick_button, alignment=Qt.AlignmentFlag.AlignLeft)
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
        launch_row = QHBoxLayout()
        launch_row.addWidget(self._launch_combo)
        launch_row.addStretch(1)

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
        frame_layout.addWidget(launch_label)
        frame_layout.addLayout(launch_row)
        frame_layout.addWidget(buttons)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.addWidget(frame)

        self._name_edit.textChanged.connect(self._validate)
        self._file_edit.textChanged.connect(self._validate)
        self._sh_edit.textChanged.connect(self._validate)
        self._file_radio.toggled.connect(self._validate)
        self._validate()
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _pick_file(self) -> None:
        start = self._file_edit.text().strip() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select script file", start)
        if path:
            self._file_edit.setText(path)

    def _validate(self) -> None:
        # A blank name, or a blank file/sh for whichever type is selected,
        # would leave the item unusable, so Save stays disabled.
        name_ok = bool(self._name_edit.text().strip())
        content_ok = (
            bool(self._sh_edit.toPlainText().strip())
            if self._sh_radio.isChecked()
            else bool(self._file_edit.text().strip())
        )
        self._save_button.setEnabled(name_ok and content_ok)

    def results(self) -> tuple[str, str | None, str | None, str]:
        """The dialog's fields as `(name, file, sh, launch)`, ready for a MenuNode."""
        name = self._name_edit.text().strip()
        launch = self._launch_combo.currentData()
        if self._sh_radio.isChecked():
            return name, None, self._sh_edit.toPlainText(), launch
        return name, self._file_edit.text().strip(), None, launch
