#!/bin/bash
# Install PyCommander desktop entry

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p ~/.local/share/applications
cp "$SCRIPT_DIR/pycommander.desktop" ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/ 2>/dev/null

echo "PyCommander desktop entry installed."
