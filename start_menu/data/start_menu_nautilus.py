#!/usr/bin/env python3
"""Start Menu's Nautilus extension: the items of its "Nautilus" folder, on the right-click menu.

Installed (copied) into ~/.local/share/nautilus-python/extensions/ by Start
Menu's Edit → Update Nautilus, and loaded by nautilus-python when Nautilus
starts. It runs inside Nautilus, under the system python3, so it imports
nothing from Start Menu and needs nothing but python3-nautilus.

Everything it offers comes from the manifest Update Nautilus writes (see
start_menu/nautilus.py), re-read on every right-click so an update takes effect
without restarting Nautilus. Picking an item runs Start Menu itself, windowless:

    <command> MENU_FILE --nautilus ITEM TARGET

which launches that item the way the Start Menu window would, with
$TARGET_FOLDER (and for a file, $TARGET_FILE) set to what was right-clicked.

Derived from Coral's coral_action.py; its structure is kept where it applies.
"""

import json
import os
import urllib.parse

from gi.repository import GLib, GObject, Nautilus  # pyright: ignore[reportMissingImports]

# Must match manifest_path() in start_menu/nautilus.py.
MANIFEST = os.path.join(
    os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
    "start-menu",
    "nautilus.json",
)


class StartMenuNautilusItems(GObject.GObject, Nautilus.MenuProvider):
    """Adds the published Start Menu items to the file and folder context menu.

    Named apart from Coral's AddNautilusMenuItems, with its own `StartMenu::`
    item-name prefix, so the two extensions can be installed side by side.
    """

    def __init__(self):
        super().__init__()

    def get_file_items(self, files):
        """Menu items for a right-clicked file or folder.

        Only for a single selection, as in Coral: an item runs on one target.
        Each item is offered on folders or on files, as its `target_type` says.
        """
        if len(files) != 1:
            return []

        file = files[0]
        path = self._get_filesystem_path(file)
        if not path:
            return []

        manifest = self._load_manifest()
        if not manifest:
            return []

        wanted = "folder" if file.is_directory() else "file"
        items = []
        for index, entry in enumerate(manifest.get("items", [])):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not name or entry.get("target_type", "folder") != wanted:
                continue
            item = Nautilus.MenuItem(
                # Numbered rather than named: a name may hold anything.
                name=f"StartMenu::item_{index}",
                label=name,
                tip=f"Run Start Menu's '{name}' on this {wanted}",
            )
            item.connect("activate", self.run_item, manifest, name, path)
            items.append(item)
        return items

    def get_background_items(self, current_folder):
        """Nothing on the empty-space menu: every item has a file or folder target."""
        return []

    def run_item(self, menu, manifest, name, path):
        """Run Start Menu, windowless, to launch item `name` on `path`.

        GLib.spawn_async rather than subprocess, as Coral does for its own
        helpers: it never blocks Nautilus, and GLib reaps the child when it
        exits. Start Menu reports any failure in a dialog of its own; its
        stderr lands in the journal (`journalctl -f | grep nautilus`).
        """
        command = manifest.get("command") or []
        menu_file = manifest.get("menu")
        if not command or not menu_file:
            print(f"Start Menu: {MANIFEST} has no command or menu file.")
            return
        argv = [*command, menu_file, "--nautilus", name, path]
        try:
            GLib.spawn_async(
                argv=argv,
                working_directory=manifest.get("cwd") or None,
                flags=GLib.SpawnFlags.SEARCH_PATH,
            )
        except GLib.Error as e:
            print(f"Start Menu: could not run {argv}: {e}")

    def _load_manifest(self):
        """The manifest as a dict, or None if it's missing or unreadable."""
        try:
            with open(MANIFEST, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            print(f"Start Menu: could not read {MANIFEST}: {e}")
            return None
        return data if isinstance(data, dict) else None

    def _get_filesystem_path(self, file_info):
        uri = file_info.get_uri()
        if not uri or not uri.startswith("file://"):
            return None
        return urllib.parse.unquote(uri[7:])
