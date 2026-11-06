#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu machine for working on Start Menu.
#
#   ./setup.sh
#
# Run it as yourself, not with sudo: it asks for your password only for the
# apt step, and uv must be installed into *your* home, not root's. Safe to run
# again — every step skips what is already done.
#
# What it sets up:
#   - apt packages: the system PyQt6 and friends that the .deb runs against
#     (so ./build.sh's smoke test can check every module), plus tmux and
#     python3-nautilus for the tmux launch mode and the Nautilus integration;
#   - uv, which ./start.sh and ./lint.sh run everything through;
#   - the windowchrome sibling checkout, which pyproject.toml needs;
#   - the project's virtualenv (.venv), including the Python version named in
#     .python-version, which uv downloads for itself.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -eq 0 ]; then
  echo "Error: run this as your own user, not root (it calls sudo itself where needed)." >&2
  exit 1
fi

# -- apt packages --------------------------------------------------------------

# python3-pyqt6, python3-yaml and libqt6svg6 are the .deb's Depends:, and
# qt6-wayland one of its Recommends:. Running from the checkout doesn't use
# them (uv installs its own PyQt6 into .venv), but build-deb.sh smoke-tests the
# package with /usr/bin/python3, and with no system PyQt6 it can only check the
# Qt-free modules. libqt6svg6 must be named: apt won't pull it in, and without
# it SVG-only theme icons (Yaru's arrows) come back empty.
#
# libxcb-cursor0 is for uv's PyQt6 rather than apt's: Qt needs it to load its
# X11 (xcb) platform plugin, which it falls back to when Wayland is unavailable
# or QT_QPA_PLATFORM=xcb is set, and which otherwise fails with "Could not load
# the Qt platform plugin xcb".
#
# fonts-noto-color-emoji draws emoji in menu names (Ubuntu usually has it
# already); tmux is for the 'tmux' launch mode; python3-nautilus for Edit →
# Update Nautilus. git and curl are needed by the steps below.
echo "==> Installing apt packages (sudo will ask for your password)"
sudo apt-get update
sudo apt-get install -y \
  git curl \
  python3 python3-pyqt6 python3-yaml libqt6svg6 qt6-wayland \
  libxcb-cursor0 fonts-noto-color-emoji \
  tmux python3-nautilus

# -- uv ------------------------------------------------------------------------

# uv isn't in Ubuntu's archive; Astral's installer puts it in ~/.local/bin and
# adds that to PATH in your shell startup files, which only a *new* terminal
# reads — so it is put on this script's PATH by hand as well.
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
  echo "==> uv already installed: $(uv --version)"
else
  echo "==> Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# -- windowchrome --------------------------------------------------------------

# pyproject.toml resolves windowchrome by path from ../windowchrome; without it
# every `uv run` fails with an unresolved path dependency.
WINDOWCHROME="$(dirname -- "$HERE")/windowchrome"
if [ -f "$WINDOWCHROME/windowchrome/__init__.py" ]; then
  echo "==> windowchrome already present at $WINDOWCHROME"
else
  echo "==> Cloning windowchrome to $WINDOWCHROME"
  git clone https://github.com/Clay-Ferguson/windowchrome.git "$WINDOWCHROME"
fi

# -- virtualenv ----------------------------------------------------------------

# A .venv copied from another machine points at that machine's Python (this
# one's had no working bin/python at all), so a .venv whose python won't run
# is removed and rebuilt. It holds nothing but what uv installs into it.
if [ -d "$HERE/.venv" ] && ! "$HERE/.venv/bin/python" --version >/dev/null 2>&1; then
  echo "==> Removing a broken .venv (its Python doesn't run on this machine)"
  rm -rf "$HERE/.venv"
fi

# ./start.sh would do this on its first run anyway; doing it here means a
# download problem shows up now rather than as a slow or failed first launch.
echo "==> Building the virtualenv"
unset VIRTUAL_ENV
uv sync --directory "$HERE"
uv run --directory "$HERE" python -c "import PyQt6.QtWidgets, yaml, windowchrome"

echo ""
echo "Setup complete. Open a new terminal (so uv is on your PATH), then:"
echo "  ./start.sh     run Start Menu from this checkout"
echo "  ./lint.sh      static checks"
echo "  ./build.sh     build the .deb, and optionally install it"
