"""Nautilus integration: the top-level "Nautilus" folder, on Nautilus's right-click menu.

Two halves, joined by a manifest file:

  publish()   Edit → Update Nautilus. Installs the extension
              (data/start_menu_nautilus.py) into nautilus-python's per-user
              extensions directory, and writes the manifest: which items to
              offer, and the command that runs Start Menu.

  extension   Runs inside Nautilus. Reads the manifest on every right-click
              and, when one of its items is picked, runs
              `start-menu MENU_FILE --nautilus ITEM TARGET` — a windowless Start
              Menu that launches that one item with $TARGET_FOLDER (and, for a
              file, $TARGET_FILE) set; see __main__._run_nautilus_item.

Why a manifest rather than the list baked into the extension: Nautilus loads
extensions only when it starts, so a changed extension means restarting
Nautilus (closing its windows), while a changed manifest is simply read on the
next right-click. Only the first publish, or one after the extension's own
code has changed, needs the restart. It also keeps the user's YAML out of the
Nautilus process altogether: a half-edited menu file can't break Nautilus.

No Qt here: the .deb's smoke test imports this on a build machine without it.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace

from . import DATA_DIR
from .menu import TARGET_FILE_TYPE, TARGET_FOLDER_TYPE, MenuNode

# The folder whose items are offered: top level only, named exactly this.
NAUTILUS_FOLDER = "Nautilus"

EXTENSION_NAME = "start_menu_nautilus.py"
EXTENSION_SOURCE = os.path.join(DATA_DIR, EXTENSION_NAME)

# What a launched item is told about the thing that was right-clicked.
TARGET_FOLDER_VAR = "TARGET_FOLDER"
TARGET_FILE_VAR = "TARGET_FILE"

# `$TARGET_FOLDER` or `${TARGET_FOLDER}` (and the same for TARGET_FILE), but
# not `$TARGET_FOLDERS` — the name has to end where the shell would end it.
_TARGET_REF_RE = re.compile(
    r"\$(?:\{(%s|%s)\}|(%s|%s)(?![A-Za-z0-9_]))"
    % ((TARGET_FOLDER_VAR, TARGET_FILE_VAR) * 2)
)

# Where the .deb puts the package and its launcher (see build-deb.sh).
INSTALLED_LIB = "/usr/lib/start-menu"
INSTALLED_LAUNCHER = "/usr/bin/start-menu"

# The package's parent directory: the checkout, or INSTALLED_LIB.
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# Where nautilus-python keeps the shared library that loads Python extensions.
# It comes from the python3-nautilus package, which nothing installs for us.
_PYTHON_NAUTILUS_GLOBS = (
    "/usr/lib/*/nautilus/extensions-*/libnautilus-python.so",
    "/usr/lib/nautilus/extensions-*/libnautilus-python.so",
)


@dataclass
class PublishResult:
    """What `publish` did, for the dialog that reports it."""

    items: list[MenuNode]
    # True when the extension file was installed or replaced, which Nautilus
    # only notices when it restarts.
    extension_changed: bool


class PublishError(Exception):
    """A Nautilus folder that can't be published as it stands."""


def _data_home() -> str:
    # nautilus-python looks under g_get_user_data_dir(), which is this.
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


def extensions_dir() -> str:
    return os.path.join(_data_home(), "nautilus-python", "extensions")


def manifest_path() -> str:
    """The manifest file. The extension computes the same path on its own."""
    return os.path.join(_data_home(), "start-menu", "nautilus.json")


def nautilus_folder(nodes: list[MenuNode]) -> MenuNode | None:
    """The first top-level section named exactly NAUTILUS_FOLDER, if any."""
    for node in nodes:
        if node.is_section and node.name == NAUTILUS_FOLDER:
            return node
    return None


def nautilus_items(nodes: list[MenuNode]) -> list[MenuNode]:
    """The items offered to Nautilus: the Nautilus folder's direct scripts.

    Sections inside it are skipped — only what sits directly in the folder
    is offered.
    """
    folder = nautilus_folder(nodes)
    if folder is None:
        return []
    return [child for child in folder.children if not child.is_section]


def find_nautilus_item(nodes: list[MenuNode], name: str, target: str) -> MenuNode | None:
    """The item named `name` that is offered on `target`'s kind (file or folder).

    By kind as well as name, so one name can serve both — a "Copy Full Path"
    for files and another for folders.
    """
    kind = target_type_of(target)
    for node in nautilus_items(nodes):
        if node.name == name and node.target_type == kind:
            return node
    return None


def target_type_of(path: str) -> str:
    """The `target_type:` an item needs to be offered on `path`."""
    return TARGET_FOLDER_TYPE if os.path.isdir(path) else TARGET_FILE_TYPE


def target_env(path: str) -> dict[str, str]:
    """The variables an item launched on `path` is given.

    A folder gets $TARGET_FOLDER. A file gets $TARGET_FILE, and its parent as
    $TARGET_FOLDER too, so `cwd: $TARGET_FOLDER` works for either kind; a
    script tells the two apart by whether $TARGET_FILE is set.
    """
    path = os.path.abspath(path)
    if os.path.isdir(path):
        return {TARGET_FOLDER_VAR: path}
    return {TARGET_FILE_VAR: path, TARGET_FOLDER_VAR: os.path.dirname(path)}


def with_target(node: MenuNode, env: dict[str, str]) -> MenuNode:
    """`node` with $TARGET_FOLDER/$TARGET_FILE filled in to its `cwd:` and `file:`.

    So `cwd: $TARGET_FOLDER` runs in the clicked folder and `file: $TARGET_FILE`
    runs the clicked file. Substituted here, not put into this process's
    environment for `MenuNode`'s own $VAR expansion to find: everything spawned
    inherits that environment, and a tmux server started by this launch would
    keep the values for good — every later tmux item, Nautilus or not, would
    see this target. The script itself gets them from `launch`'s `exports`.
    """

    def substitute(text: str | None) -> str | None:
        if text is None:
            return None
        return _TARGET_REF_RE.sub(lambda m: env.get(m.group(1) or m.group(2), m.group(0)), text)

    return replace(node, cwd=substitute(node.cwd), file=substitute(node.file))


def launcher_command() -> tuple[list[str], str]:
    """The command that runs this Start Menu, and the directory to run it in.

    An installed copy runs through its own launcher. A checkout runs its
    virtualenv's python directly rather than start.sh: that needs `uv`, which
    usually lives in ~/.local/bin, and Nautilus's PATH usually lacks it. `-m`
    finds the package through the working directory, hence the checkout as cwd.
    """
    if PACKAGE_ROOT == INSTALLED_LIB and os.path.isfile(INSTALLED_LAUNCHER):
        return [INSTALLED_LAUNCHER], PACKAGE_ROOT
    return [sys.executable, "-m", "start_menu"], PACKAGE_ROOT


def python_nautilus_available() -> bool:
    return any(glob.glob(pattern) for pattern in _PYTHON_NAUTILUS_GLOBS)


def publish(menu_path: str, nodes: list[MenuNode]) -> PublishResult:
    """Install the extension and write the manifest for `nodes`' Nautilus folder.

    Items are found again by name and target type when one is picked (see
    `find_nautilus_item`), so two sharing both would be ambiguous: that is
    refused (PublishError) before anything is written. No Nautilus folder at
    all publishes an empty list, which takes Start Menu's items back off
    Nautilus's menu. Raises OSError if a file can't be written.
    """
    items = nautilus_items(nodes)
    keys = [(item.name, item.target_type) for item in items]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        listed = "\n".join(f'  • "{name}" (for {kind}s)' for name, kind in duplicates)
        raise PublishError(
            f"The {NAUTILUS_FOLDER} folder has more than one item of the same name "
            f"for the same target:\n\n{listed}\n\n"
            "Nautilus finds an item by its name, so one name can be used at most "
            "once for files and once for folders. Rename one and try again."
        )

    with open(EXTENSION_SOURCE, "rb") as f:
        extension = f.read()
    installed = os.path.join(extensions_dir(), EXTENSION_NAME)
    try:
        with open(installed, "rb") as f:
            extension_changed = f.read() != extension
    except OSError:
        extension_changed = True
    if extension_changed:
        _write_atomic(installed, extension)

    command, cwd = launcher_command()
    manifest = {
        "command": command,
        "cwd": cwd,
        "menu": os.path.abspath(menu_path),
        "items": [{"name": item.name, "target_type": item.target_type} for item in items],
    }
    _write_atomic(manifest_path(), (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    return PublishResult(items=items, extension_changed=extension_changed)


def clear() -> bool:
    """Edit → Clear Nautilus: undo `publish`. True if anything was removed.

    Deletes the manifest and the installed extension. The manifest going is
    what takes the items off at once: an extension Nautilus already loaded
    finds no manifest on the next right-click and offers nothing, so no
    restart is needed. The extension going means it isn't loaded at all from
    the next start on. A later publish reinstalls both (and, the extension
    being new again, offers the restart). Raises OSError if one can't be
    deleted.
    """
    removed = False
    for path in (manifest_path(), os.path.join(extensions_dir(), EXTENSION_NAME)):
        try:
            os.unlink(path)
            removed = True
        except FileNotFoundError:
            pass
    return removed


def restart_nautilus() -> str | None:
    """Quit Nautilus so it loads the extension when it next opens. Error, or None."""
    try:
        subprocess.Popen(
            ["nautilus", "-q"],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return f"Could not run 'nautilus -q':\n\n{exc}"
    return None


def _write_atomic(path: str, data: bytes) -> None:
    """Write `path` via a temp file and os.replace.

    Nautilus may read either file at any moment — the manifest on every
    right-click — so it must never see one half-written.
    """
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".start-menu-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
