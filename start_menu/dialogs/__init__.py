"""Editing dialogs opened from the tree's per-row action icons.

One module per editable thing: a folder's name (`FolderNameDialog` in
`folder_name.py`, shared between renaming an existing folder and naming a
brand new one), and a launchable item's name/file-or-sh/cwd/launch mode
(`ItemEditDialog` in `item_edit.py`, same reuse between edit and create).
`style.py` holds the frame and input styling both of them draw. Item
reordering has no dialog of its own — it's driven straight from the row's
up/down icons.

Both classes are re-exported here, so callers import them from the package
(`from .dialogs import ItemEditDialog`) without caring which module they
live in.
"""

from __future__ import annotations

from .folder_name import FolderNameDialog
from .item_edit import ItemEditDialog

__all__ = ["FolderNameDialog", "ItemEditDialog"]
