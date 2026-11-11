"""The dialog for naming a section ('folder:') entry."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)
from windowchrome import apply_frame

from .style import BUTTON_STYLE, LABEL_STYLE, field_style


class FolderNameDialog(QDialog):
    """A single text field for naming a section ('folder:') entry.

    Reused for both renaming an existing folder and naming a new one — the
    `title` decides which, since the field itself is identical either way.
    """

    def __init__(
        self, current_name: str, parent: QWidget | None = None, title: str = "Rename"
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(440, 220)
        # windowchrome's title bar and border (README §13). The border is also
        # what keeps a dialog this small from losing its edge against the
        # desktop behind it, which an inner bordered QFrame used to do.
        apply_frame(self)

        self._name_edit = QLineEdit(current_name)
        self._name_edit.setStyleSheet(field_style())
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(14)
        layout.addWidget(label)
        layout.addWidget(self._name_edit)
        layout.addStretch(1)
        layout.addWidget(buttons)

        self._name_edit.textChanged.connect(self._validate)
        self._validate()
        self._name_edit.setFocus()

    def _validate(self) -> None:
        # A blank name would leave the item unlabeled, so Save stays disabled.
        self._save_button.setEnabled(bool(self._name_edit.text().strip()))

    def new_name(self) -> str:
        return self._name_edit.text().strip()
