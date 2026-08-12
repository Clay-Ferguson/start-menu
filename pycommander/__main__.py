"""Entry point: python -m pycommander [--menu FILE]"""

from __future__ import annotations

import argparse
import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME
from .menu import MenuError, load_menu
from .window import MainWindow, format_errors

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DEFAULT_MENU = os.path.join(PROJECT_ROOT, "menu.yaml")
ICON = os.path.join(PROJECT_ROOT, "pycommander.png")


def main() -> int:
    parser = argparse.ArgumentParser(prog="pycommander", description=__doc__)
    parser.add_argument(
        "--menu",
        default=DEFAULT_MENU,
        metavar="FILE",
        help=f"menu definition to load (default: {DEFAULT_MENU})",
    )
    args = parser.parse_args()
    menu_path = os.path.abspath(os.path.expanduser(args.menu))

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    # Ties the window to pycommander.desktop, so the desktop shows our icon in
    # the dock and alt-tab instead of a generic one. Without it the Wayland
    # app_id is derived from argv[0] ("python3") and matches nothing.
    app.setDesktopFileName("pycommander")
    if os.path.isfile(ICON):
        app.setWindowIcon(QIcon(ICON))

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
