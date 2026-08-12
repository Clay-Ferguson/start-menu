#!/bin/bash
# Uninstall PyCommander desktop entry

DESKTOP_TARGET="$HOME/.local/share/applications/pycommander.desktop"

if [ -f "$DESKTOP_TARGET" ]; then
  rm -f "$DESKTOP_TARGET"
  update-desktop-database "$HOME/.local/share/applications/" 2>/dev/null
  echo "PyCommander desktop entry removed."
else
  echo "PyCommander desktop entry not found."
fi
