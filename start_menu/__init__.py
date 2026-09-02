"""Start Menu: a keyboard-driven menu/launcher defined by a single YAML file."""

from windowchrome import ChromeTheme

APP_NAME = "Start Menu"

# A launcher is read at a glance from across the desk, not studied, so this
# runs a few points above the desktop default. Shared by the menu view and
# its editing dialogs so they read as one piece of UI.
UI_POINT_SIZE = 15

# The window's title bar, and with it the thin frame the decoration draws down
# the sides and along the bottom. `windowchrome` owns both — see
# `../windowchrome/README.md` for why they are reachable at all (Wayland only,
# by repurposing three palette roles) and why their *size* is not.
#
# The library ships neutral defaults; this is Start Menu's override of them,
# and it deliberately matches the other apps here so they read as one family
# rather than as unrelated windows.
START_MENU_THEME = ChromeTheme(title_bg="#1369da")
