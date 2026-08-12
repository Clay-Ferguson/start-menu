#!/bin/bash
# Install PyCommander desktop entry
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

read -rp "Path to the PyCommander program directory [$SCRIPT_DIR]: " PROGRAM_DIR
PROGRAM_DIR="${PROGRAM_DIR:-$SCRIPT_DIR}"
PROGRAM_DIR="${PROGRAM_DIR/#\~/$HOME}"
PROGRAM_DIR="$(cd "$PROGRAM_DIR" && pwd)"  # normalize; fails if it doesn't exist

DEFAULT_MENU="$PROGRAM_DIR/menu.yaml"
read -rp "Path to your menu.yaml file [$DEFAULT_MENU]: " MENU_FILE
MENU_FILE="${MENU_FILE:-$DEFAULT_MENU}"
MENU_FILE="${MENU_FILE/#\~/$HOME}"  # expand ~ without requiring the file to exist yet
case "$MENU_FILE" in
  /*) ;;
  *) MENU_FILE="$PWD/$MENU_FILE" ;;
esac

mkdir -p ~/.local/share/applications
DESKTOP_TARGET="$HOME/.local/share/applications/pycommander.desktop"

sed \
  -e "s|^Exec=.*|Exec=\"$PROGRAM_DIR/start.sh\" \"$MENU_FILE\"|" \
  -e "s|^Icon=.*|Icon=$PROGRAM_DIR/pycommander.png|" \
  "$SCRIPT_DIR/pycommander.desktop" > "$DESKTOP_TARGET"
update-desktop-database ~/.local/share/applications/ 2>/dev/null

echo "PyCommander desktop entry installed."
echo "  Program:   $PROGRAM_DIR"
echo "  Menu file: $MENU_FILE"
if [ ! -f "$MENU_FILE" ]; then
  echo "  (menu.yaml doesn't exist yet — PyCommander will create it, with a starter example, the first time it runs)"
fi
