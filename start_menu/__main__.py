"""Entry point: python -m start_menu [MENU_FILE] [--nautilus ITEM TARGET]"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import traceback
from functools import partial

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, DATA_DIR
from .launcher import launch
from .menu import (
    LAUNCH_HOLD,
    MenuError,
    MenuNode,
    Options,
    dump_menu,
    format_errors,
    load_menu,
)
from .nautilus import (
    NAUTILUS_FOLDER,
    find_nautilus_item,
    target_env,
    target_type_of,
    with_target,
)
from .window import MainWindow, ask_running_session

# The window's own icon. An installed copy also gets its dock icon from the
# themed icons the .deb installs; a checkout run has only this.
ICON = os.path.join(DATA_DIR, "start-menu.png")

# The color emoji font Qt 6.4 is pointed at (see main()). The .deb Recommends
# its package, fonts-noto-color-emoji, which Ubuntu installs by default.
EMOJI_FONT = "Noto Color Emoji"

# Where the menu lives when no path is given on the command line. A system-wide
# install (the .deb) puts one desktop entry in front of every user on the
# machine, so its Exec= line can't carry anyone's personal path — this is what
# it launches, and what makes the packaged entry work for a stranger.
DEFAULT_MENU = os.path.expanduser("~/.config/start-menu/menu.yaml")

# The example menu, which seeds a menu file that doesn't exist yet.
EXAMPLE_MENU = os.path.join(DATA_DIR, "example-menu.yaml")

STARTER_ITEM_NAME = "Example"

# How much of a traceback the internal-error dialog shows.
TRACEBACK_LINES = 12


def _create_menu_file(path: str) -> None:
    """Create a menu file at `path`, so pointing at one that isn't there works.

    Normally a copy of the bundled example, which is worth a great deal more
    than a blank menu to someone opening Start Menu for the first time: it is a
    working menu *and* a commented reference to build their own from. It is
    copied byte for byte rather than round-tripped through load_menu/dump_menu,
    which would drop the comments that are most of its value.

    The fallback, for an install whose example has gone missing, is a single
    harmless item: the top-level menu can't be empty (load_menu rejects that),
    so there has to be something.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if os.path.isfile(EXAMPLE_MENU):
        shutil.copyfile(EXAMPLE_MENU, path)
        return
    starter = [
        MenuNode(
            name=STARTER_ITEM_NAME,
            sh='echo "Edit this menu to add your own items."',
            launch=LAUNCH_HOLD,
            cwd="~",
        )
    ]
    dump_menu(path, starter, Options())


def _report_unhandled(kind, value, trace) -> None:
    """Show an exception that escaped a slot, instead of dying of it.

    PyQt6 aborts the whole process when a Python exception leaves a slot and
    no `sys.excepthook` has been installed — a bug behind one button would
    close the menu outright, with nothing to show for it when Start Menu was
    started from a desktop icon. With a hook installed PyQt calls it instead
    and carries on, so the bug is reported and the window survives.
    """
    text = "".join(traceback.format_exception(kind, value, trace))
    if sys.__stderr__ is not None:
        sys.__stderr__.write(text)
    if QApplication.instance() is None:
        return
    # The tail of the traceback, where the failing line is: a desktop launch
    # has no terminal for the stderr copy above to reach.
    tail = "\n".join(text.rstrip().splitlines()[-TRACEBACK_LINES:])
    QMessageBox.critical(
        None,
        f"{APP_NAME} — internal error",
        f"Something went wrong inside {APP_NAME}. The window should still "
        f"work.\n\n{tail}",
    )


def main() -> int:
    # menu_file is optional because there is a default. That is what lets the
    # packaged desktop entry name no file at all: one Exec= line serves every
    # user on the machine precisely because none of them appears in it.
    parser = argparse.ArgumentParser(prog="start-menu", description=__doc__)
    parser.add_argument(
        "menu_file",
        nargs="?",
        default=None,
        metavar="MENU_FILE",
        help=f"path to the menu YAML file to load (default: {DEFAULT_MENU}); "
        "created from the bundled example menu if it doesn't exist yet",
    )
    # What the Nautilus extension runs when one of its items is picked (see
    # nautilus.py): no window, just that one launch.
    parser.add_argument(
        "--nautilus",
        nargs=2,
        metavar=("ITEM", "TARGET"),
        help=f"launch ITEM from the menu's '{NAUTILUS_FOLDER}' folder on the file "
        "or folder TARGET, without opening the window",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    sys.excepthook = _report_unhandled
    app.setApplicationName(APP_NAME)
    # applicationDisplayName is deliberately NOT set. Every platform backend
    # runs window titles through QPlatformWindow::formatWindowTitle(), which
    # appends the display name to any title that isn't exactly it — so with
    # it set, "Start Menu — launch failed" reached the title bar as
    # "Start Menu — launch failed — Start Menu". Each window spells out its
    # own full title instead.
    # Ties the window to start-menu.desktop, so the desktop shows our icon in
    # the dock and alt-tab instead of a generic one. Without it the Wayland
    # app_id is derived from argv[0] ("python3") and matches nothing.
    app.setDesktopFileName("start-menu")
    if os.path.isfile(ICON):
        app.setWindowIcon(QIcon(ICON))
    # Names may start with a color emoji ("🔧  VSCode"), the trick that gives a
    # Nautilus item an icon. Qt 6.9+ (the uv venv) sends emoji to a color
    # emoji font on its own; Qt 6.4 (the .deb, apt's python3-pyqt6) falls back
    # by script, never picks the emoji font, and draws a box. Naming it as the
    # app font's last fallback fixes 6.4 and changes nothing on newer Qt.
    # Every widget font derives from the app font, so all of them inherit it.
    # A family that isn't installed is simply skipped.
    font = app.font()
    font.setFamilies([*font.families(), EMOJI_FONT])
    app.setFont(font)

    menu_path = os.path.abspath(os.path.expanduser(args.menu_file or DEFAULT_MENU))

    if args.nautilus:
        item, target = args.nautilus
        return _run_nautilus_item(menu_path, item, target)

    if not os.path.exists(menu_path):
        try:
            _create_menu_file(menu_path)
        except OSError as exc:
            QMessageBox.critical(
                None, f"{APP_NAME} — cannot start", f"Could not create {menu_path}:\n\n{exc}"
            )
            return 1

    loaded = _load_or_report(menu_path, f"{APP_NAME} — cannot start")
    if loaded is None:
        return 1
    nodes, options = loaded

    window = MainWindow(menu_path, nodes, options)
    window.show()
    window.activateWindow()
    window.raise_()
    return app.exec()


def _load_or_report(menu_path: str, title: str) -> tuple[list[MenuNode], Options] | None:
    """`load_menu`, with any failure shown in a dialog titled `title` (then None)."""
    try:
        nodes, options, errors = load_menu(menu_path)
    except MenuError as exc:
        QMessageBox.critical(None, title, str(exc))
        return None
    if errors:
        QMessageBox.critical(None, title, format_errors(menu_path, errors))
        return None
    return nodes, options


def _run_nautilus_item(menu_path: str, name: str, target: str) -> int:
    """Launch Nautilus-folder item `name` on `target`, with no window: --nautilus.

    Run by the Nautilus extension, so everything goes wrong in a dialog, and
    the process ends as soon as the launch is under way — launched scripts
    have their own session and outlive it, just as they outlive the window.

    A missing menu file is an error here rather than being seeded from the
    example: the extension names the file it was published from, and a new
    copy of the example would not hold the item asked for anyway.
    """
    title = f"{APP_NAME} — cannot run '{name}'"
    if not os.path.exists(target):
        QMessageBox.critical(None, title, f"{target}\n\nNo such file or folder.")
        return 1
    loaded = _load_or_report(menu_path, title)
    if loaded is None:
        return 1
    nodes, _ = loaded

    node = find_nautilus_item(nodes, name, target)
    if node is None:
        QMessageBox.critical(
            None,
            title,
            f"There is no item named '{name}' for {target_type_of(target)}s in the "
            f"'{NAUTILUS_FOLDER}' folder of\n{menu_path}.\n\n"
            "It was probably renamed or removed after Nautilus's menu was last "
            f"updated. Open {APP_NAME}, switch on Edit, and choose "
            "Edit → Update Nautilus.",
        )
        return 1

    env = target_env(target)
    error = launch(
        with_target(node, env),
        on_running_session=partial(ask_running_session, None),
        exports=env,
    )
    if error:
        QMessageBox.critical(None, f"{APP_NAME} — launch failed", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
