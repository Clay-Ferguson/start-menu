"""Entry point: python -m start_menu MENU_FILE"""

from __future__ import annotations

import argparse
import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME
from .menu import LAUNCH_HOLD, MenuError, MenuNode, Options, dump_menu, load_menu
from .window import MainWindow, format_errors

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ICON = os.path.join(PROJECT_ROOT, "start-menu.png")

STARTER_ITEM_NAME = "Example"


def _create_starter_menu(path: str) -> None:
    """Write a minimal menu.yaml at `path`, so pointing at a fresh file just works.

    The top-level menu can't be empty (load_menu rejects that), so this seeds
    one harmless example item rather than an empty list — something to look
    at and edit rather than a blank file.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    starter = [
        MenuNode(
            name=STARTER_ITEM_NAME,
            sh='echo "Edit this menu to add your own items."',
            launch=LAUNCH_HOLD,
            cwd="~",
        )
    ]
    dump_menu(path, starter, Options())


def main() -> int:
    # menu_file is nargs="?" rather than required: argparse's own handling of a
    # missing required argument prints to stderr and exits before a QApplication
    # exists, which is invisible when launched from a desktop icon rather than a
    # terminal. Left optional here, the missing-argument case is instead reported
    # with a QMessageBox below, once the app exists to show one.
    parser = argparse.ArgumentParser(prog="start-menu", description=__doc__)
    parser.add_argument(
        "menu_file",
        nargs="?",
        default=None,
        metavar="MENU_FILE",
        help="path to the menu YAML file to load; created with a starter example if it doesn't exist yet",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    # Ties the window to start-menu.desktop, so the desktop shows our icon in
    # the dock and alt-tab instead of a generic one. Without it the Wayland
    # app_id is derived from argv[0] ("python3") and matches nothing.
    app.setDesktopFileName("start-menu")
    if os.path.isfile(ICON):
        app.setWindowIcon(QIcon(ICON))

    if args.menu_file is None:
        QMessageBox.warning(
            None,
            f"{APP_NAME} — no menu file",
            "Start Menu needs a menu file to run.\n\n"
            "Usage: start-menu MENU_FILE\n\n"
            "Pass the full path to your menu.yaml as a command-line argument "
            "(start.sh or the desktop entry's Exec= line is where this is set).",
        )
        return 1

    menu_path = os.path.abspath(os.path.expanduser(args.menu_file))

    if not os.path.exists(menu_path):
        try:
            _create_starter_menu(menu_path)
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
