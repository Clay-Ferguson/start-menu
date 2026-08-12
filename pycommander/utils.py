"""Generic helpers with no natural home in menu/launcher/window/dialogs.

Currently just `open_in_editor`, shared by the "e" shortcut that opens the
whole menu.yaml (window.py) and the "Edit" button on a script item's file
path (dialogs.py).
"""

from __future__ import annotations

import os
import shlex
import shutil

from .launcher import launch
from .menu import LAUNCH_DETACHED, MenuNode


def open_in_editor(path: str, editor: str) -> str | None:
    """Open `path` in `editor`. Returns an error message, or None on success.

    Routed through launch() as a detached inline snippet, so the editor is
    spawned exactly the way a `launch: detached` menu item would be — its own
    session, surviving PyCommander. `editor` is shell text, so it may carry
    arguments of its own.
    """
    binary = shlex.split(editor)[0] if editor.strip() else ""
    if not binary or not shutil.which(binary):
        return (
            f"Cannot open '{path}':\n\n"
            f"The editor '{binary or editor}' was not found on PATH.\n\n"
            f"Set 'editor:' under 'options:' in the menu file to one you have."
        )
    node = MenuNode(
        name=os.path.basename(path),
        sh=f"{editor} {shlex.quote(path)}",
        launch=LAUNCH_DETACHED,
        cwd=os.path.dirname(path),
    )
    return launch(node)
