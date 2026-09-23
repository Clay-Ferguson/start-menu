"""Entry point: python -m start_menu [MENU_FILE]"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import traceback

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME
from .menu import LAUNCH_HOLD, MenuError, MenuNode, Options, dump_menu, load_menu
from .window import MainWindow, format_errors

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ICON = os.path.join(PROJECT_ROOT, "start-menu.png")

# Where the menu lives when no path is given on the command line. A system-wide
# install (the .deb) puts one desktop entry in front of every user on the
# machine, so its Exec= line can't carry anyone's personal path — this is what
# it launches, and what makes the packaged entry work for a stranger.
DEFAULT_MENU = os.path.expanduser("~/.config/start-menu/menu.yaml")

# The example menu, shipped beside the package: <checkout>/menu.yaml from a git
# checkout, /usr/lib/start-menu/menu.yaml from the .deb. Found through
# PROJECT_ROOT exactly as ICON is, and for the same reason neither file may be
# moved out from beside the package directory.
EXAMPLE_MENU = os.path.join(PROJECT_ROOT, "menu.yaml")

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

    The fallback, for a checkout whose example has been deleted, is a single
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

    menu_path = os.path.abspath(os.path.expanduser(args.menu_file or DEFAULT_MENU))

    if not os.path.exists(menu_path):
        try:
            _create_menu_file(menu_path)
        except OSError as exc:
            QMessageBox.critical(
                None, f"{APP_NAME} — cannot start", f"Could not create {menu_path}:\n\n{exc}"
            )
            return 1

    try:
        nodes, options, errors = load_menu(menu_path)
    except MenuError as exc:
        QMessageBox.critical(None, f"{APP_NAME} — cannot start", str(exc))
        return 1
    if errors:
        QMessageBox.critical(
            None, f"{APP_NAME} — cannot start", format_errors(menu_path, errors)
        )
        return 1

    window = MainWindow(menu_path, nodes, options)
    window.show()
    window.activateWindow()
    window.raise_()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
