#!/bin/bash
# Uninstall Start Menu desktop entry

DESKTOP_TARGET="$HOME/.local/share/applications/start-menu.desktop"

if [ -f "$DESKTOP_TARGET" ]; then
  rm -f "$DESKTOP_TARGET"
  update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null
  echo "Start Menu desktop entry removed."
else
  echo "Start Menu desktop entry not found."
fi
