#!/usr/bin/env bash
# Build a Debian package (.deb) of Start Menu.
#
# Usage:  ./build-deb-install.sh
# Output: dist/start-menu_<version>_all.deb
# Then:   sudo apt install ./dist/start-menu_<version>_all.deb
#
# Built by hand with dpkg-deb rather than with debhelper: Start Menu is pure
# Python with no build step, so all the package has to do is put files in the
# right places and name its dependencies. PyQt6 and PyYAML come from the
# distribution (python3-pyqt6, python3-yaml) rather than being bundled, which
# keeps the package architecture-independent and tiny. windowchrome isn't
# packaged anywhere, so its source is copied in from the sibling checkout.
#
# Installed layout:
#   /usr/bin/start-menu                         launcher
#   /usr/lib/start-menu/start_menu/             the app, including dialogs/
#   /usr/lib/start-menu/windowchrome/           copy of ../windowchrome
#   /usr/lib/start-menu/menu.yaml               example menu   } found through
#   /usr/lib/start-menu/start-menu.png          window icon    } __main__.PROJECT_ROOT
#   /usr/share/applications/start-menu.desktop  menu entry
#   /usr/share/pixmaps/start-menu.png           menu icon (symlink)
#
# Note that the Debian package is "start-menu" while the Python package it
# installs is "start_menu" — hyphen in the paths, underscore in the import.
set -euo pipefail

# Every directory the package creates must be 755 and every file 644 or 755,
# whatever the builder's own umask is (Ubuntu's default 002 would otherwise
# leave /usr, /usr/lib and friends group-writable in the package).
umask 022

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WINDOWCHROME="$HERE/../windowchrome/windowchrome"
DIST="$HERE/dist"
PACKAGE=start-menu
ARCH=all

die() {
  echo "Error: $*" >&2
  exit 1
}

command -v dpkg-deb >/dev/null 2>&1 || die "dpkg-deb not found (it is part of dpkg, on every Debian-based system)."

VERSION="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$HERE/pyproject.toml" | head -n 1)"
[ -n "$VERSION" ] || die "could not read the version from pyproject.toml."

[ -f "$WINDOWCHROME/__init__.py" ] || die "windowchrome not found at $WINDOWCHROME.
Clone it beside this folder:  git clone https://github.com/Clay-Ferguson/windowchrome.git ../windowchrome"

# The Maintainer field is whoever builds the package, taken from git unless
# START_MENU_MAINTAINER="Name <email>" says otherwise.
if [ -z "${START_MENU_MAINTAINER:-}" ]; then
  name="$(git -C "$HERE" config user.name || true)"
  email="$(git -C "$HERE" config user.email || true)"
  [ -n "$name" ] && [ -n "$email" ] || die "set git user.name and user.email, or START_MENU_MAINTAINER=\"Name <email>\"."
  START_MENU_MAINTAINER="$name <$email>"
fi

STAGE="$DIST/${PACKAGE}_${VERSION}_${ARCH}"
DEB="$DIST/${PACKAGE}_${VERSION}_${ARCH}.deb"
LIB="$STAGE/usr/lib/$PACKAGE"
rm -rf "$STAGE" "$DEB"

# -- files -------------------------------------------------------------------

install -d -m 755 \
  "$LIB/start_menu" "$LIB/start_menu/dialogs" "$LIB/windowchrome" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/pixmaps" \
  "$STAGE/usr/share/doc/$PACKAGE" \
  "$STAGE/DEBIAN"

# Copied per directory, so a new subpackage under start_menu/ (or in
# windowchrome) needs another line here or it silently won't ship.
# __pycache__ is left behind on purpose and compiled fresh by postinst.
install -m 644 "$HERE"/start_menu/*.py "$LIB/start_menu/"
install -m 644 "$HERE"/start_menu/dialogs/*.py "$LIB/start_menu/dialogs/"
install -m 644 "$WINDOWCHROME"/*.py "$LIB/windowchrome/"

# menu.yaml is the example, which __main__.EXAMPLE_MENU copies to
# ~/.config/start-menu/menu.yaml the first time a user runs Start Menu.
install -m 644 "$HERE/menu.yaml" "$HERE/start-menu.png" "$LIB/"
ln -s "../../lib/$PACKAGE/start-menu.png" "$STAGE/usr/share/pixmaps/start-menu.png"
install -m 644 "$HERE/LICENSE.md" "$STAGE/usr/share/doc/$PACKAGE/copyright"

# -I (isolated mode) keeps PYTHONPATH and ~/.local site-packages out, so the app
# always runs against the distribution's python3-pyqt6 and python3-yaml rather
# than a pip-installed copy that happens to be lying around. "$@" passes a menu
# file path through, so `start-menu /path/to/other.yaml` still works.
cat > "$STAGE/usr/bin/$PACKAGE" <<'EOF'
#!/bin/sh
# Start Menu launcher, installed by the start-menu package.
exec /usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "/usr/lib/start-menu"); from start_menu.__main__ import main; sys.exit(main())' "$@"
EOF
chmod 755 "$STAGE/usr/bin/$PACKAGE"

# The desktop entry, pointed at the installed launcher and the icon by name
# (found in /usr/share/pixmaps). No menu file on the Exec= line: one entry
# serves every user on the machine, so each gets their own
# ~/.config/start-menu/menu.yaml instead. The template's comment lines are
# dropped, since they only describe the template.
sed \
  -e '/^#/d' \
  -e "s|^Exec=.*|Exec=$PACKAGE|" \
  -e "s|^Icon=.*|Icon=$PACKAGE|" \
  "$HERE/start-menu.desktop" > "$STAGE/usr/share/applications/start-menu.desktop"
chmod 644 "$STAGE/usr/share/applications/start-menu.desktop"

# -- package metadata --------------------------------------------------------

# Compiled as root at install time, since a user running Start Menu can't write
# __pycache__ under /usr/lib; without it every launch compiles in memory.
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  python3 -m compileall -q /usr/lib/start-menu >/dev/null 2>&1 || true
fi
EOF

# Removes what postinst compiled, so dpkg can remove the directories it
# installed (it only deletes files it knows about). Runs before upgrades too;
# the new version's postinst compiles again.
cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
find /usr/lib/start-menu -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"

INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)"

# A terminal emulator is needed by the 'terminal' and 'hold' launch modes and
# tmux by the 'tmux' mode, but neither is a hard dependency: launcher.py checks
# for them and explains itself in a dialog, so a machine that never uses those
# modes has no reason to carry them.
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.11), python3-pyqt6, python3-yaml
Recommends: qt6-wayland, x-terminal-emulator
Suggests: tmux
Maintainer: $START_MENU_MAINTAINER
Installed-Size: $INSTALLED_SIZE
Homepage: https://github.com/Clay-Ferguson/start-menu
Description: keyboard-driven menu for launching your own scripts
 Start Menu shows a menu of your scripts and commands, one level at a time,
 driven by four keys: up and down to move, right to open a section, left to
 go back, Enter to launch. The whole menu is one YAML file, editable from
 inside the app or in a text editor, and each item can run detached, in a
 terminal window, in a window that stays open, or in a tmux session.
EOF

# -- build -------------------------------------------------------------------

# --root-owner-group: files owned by root without needing fakeroot.
# -Zxz: every dpkg can read xz; Ubuntu's default zstd is not readable by
# older Debian dpkg releases.
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$DEB" >/dev/null
rm -rf "$STAGE"

echo "Built $DEB"
echo ""
echo "Install:  sudo apt install $DEB"
echo "Remove:   sudo apt remove $PACKAGE"
