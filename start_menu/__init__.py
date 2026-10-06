"""Start Menu: a keyboard-driven menu/launcher defined by a single YAML file."""

import os

APP_NAME = "Start Menu"

# A launcher is read at a glance from across the desk, not studied, so this
# runs a few points above the desktop default. Shared by the menu view and
# its editing dialogs so they read as one piece of UI.
UI_POINT_SIZE = 15

# Files the program reads at run time, kept inside the package so they travel
# with it — the same place in a checkout and under /usr/lib/start-menu, with
# nothing for the .deb to copy separately. Here rather than in __main__ so the
# Qt-free modules (nautilus.py) can find them without importing Qt.
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data")
