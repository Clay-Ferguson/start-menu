#!/usr/bin/env bash
# Build a Debian package (.deb) of Start Menu.
#
# Usage:  packaging/build-deb.sh             (from anywhere)
# Output: dist/start-menu_<version>_all.deb  (dist/ at the top of the checkout)
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
#   /usr/bin/start-menu                              launcher
#   /usr/lib/start-menu/start_menu/                  the app, including data/
#                                                    (the example menu and
#                                                    the window icon)
#   /usr/lib/start-menu/windowchrome/                copy of ../windowchrome
#   /usr/share/applications/start-menu.desktop       menu entry
#   /usr/share/icons/hicolor/*/apps/start-menu.png   themed icon, every size
#
# Note that the Debian package is "start-menu" while the Python package it
# installs is "start_menu" — hyphen in the paths, underscore in the import.
# __main__ calls setDesktopFileName("start-menu") to tie the window to the
# desktop entry, so renaming either one breaks the icon in the dock.
set -euo pipefail

# Every directory the package creates must be 755 and every file 644 or 755,
# whatever the builder's own umask is (Ubuntu's default 002 would otherwise
# leave /usr, /usr/lib and friends group-writable in the package).
umask 022

# HERE is packaging/, which holds what only the package needs (this script, the
# desktop entry template, the icons); ROOT is the checkout, which holds the app.
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname -- "$HERE")"
WINDOWCHROME="$ROOT/../windowchrome/windowchrome"
DIST="$ROOT/dist"
PACKAGE=start-menu
ARCH=all

die() {
  echo "Error: $*" >&2
  exit 1
}

command -v dpkg-deb >/dev/null 2>&1 || die "dpkg-deb not found (it is part of dpkg, on every Debian-based system)."

VERSION="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$ROOT/pyproject.toml" | head -n 1)"
[ -n "$VERSION" ] || die "could not read the version from pyproject.toml."

[ -f "$WINDOWCHROME/__init__.py" ] || die "windowchrome not found at $WINDOWCHROME.
Clone it beside the start-menu checkout:  git clone https://github.com/Clay-Ferguson/windowchrome.git ../windowchrome"

# The Maintainer field is whoever builds the package, taken from git unless
# START_MENU_MAINTAINER="Name <email>" says otherwise.
if [ -z "${START_MENU_MAINTAINER:-}" ]; then
  name="$(git -C "$ROOT" config user.name || true)"
  email="$(git -C "$ROOT" config user.email || true)"
  [ -n "$name" ] && [ -n "$email" ] || die "set git user.name and user.email, or START_MENU_MAINTAINER=\"Name <email>\"."
  START_MENU_MAINTAINER="$name <$email>"
fi

STAGE="$DIST/${PACKAGE}_${VERSION}_${ARCH}"
DEB="$DIST/${PACKAGE}_${VERSION}_${ARCH}.deb"
LIB="$STAGE/usr/lib/$PACKAGE"
rm -rf "$STAGE" "$DEB"

# -- files -------------------------------------------------------------------

install -d -m 755 \
  "$LIB" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/doc/$PACKAGE" \
  "$STAGE/DEBIAN"

# Copy every file of a directory tree into the stage: files 644, and the
# directories `install -D` creates for them 755 (the umask above). Whole trees
# rather than a glob per directory, so a new module, subpackage or data file
# ships without anyone having to remember a line here — a per-directory copy
# would leave it out of a package that installs cleanly and fails on first
# use. __pycache__ is left behind on purpose and compiled fresh by postinst.
copy_tree() {
  local src="$1" dest="$2" file
  while IFS= read -r -d '' file; do
    install -D -m 644 "$src/$file" "$dest/$file"
  done < <(cd "$src" && find . -name __pycache__ -prune -o -type f -print0)
}

copy_tree "$ROOT/start_menu" "$LIB/start_menu"
copy_tree "$WINDOWCHROME" "$LIB/windowchrome"

install -m 644 "$ROOT/LICENSE.md" "$STAGE/usr/share/doc/$PACKAGE/copyright"

# Icon=start-menu in the desktop entry is a *theme* name, not a path, so the
# PNGs have to land in the hicolor theme for it to resolve. They are checked
# in at every size rather than converted here, which keeps this script free of
# Pillow and ImageMagick; regenerate them with packaging/icons/make-icons.py if
# the artwork changes. (icons/source.png is that artwork and is not installed.)
for icon in "$HERE"/icons/hicolor/*/apps/start-menu.png; do
  size_dir="$(basename "$(dirname "$(dirname "$icon")")")"
  install -d -m 755 "$STAGE/usr/share/icons/hicolor/$size_dir/apps"
  install -m 644 "$icon" "$STAGE/usr/share/icons/hicolor/$size_dir/apps/start-menu.png"
done

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

# The desktop entry, pointed at the installed launcher. No menu file on the
# Exec= line: one entry serves every user on the machine, so each gets their
# own ~/.config/start-menu/menu.yaml instead. Icon= is already the theme name
# and is rewritten only to keep it pinned to $PACKAGE. The template's comment
# lines are dropped, since they only describe the template.
sed \
  -e '/^#/d' \
  -e "s|^Exec=.*|Exec=$PACKAGE|" \
  -e "s|^Icon=.*|Icon=$PACKAGE|" \
  "$HERE/start-menu.desktop" > "$STAGE/usr/share/applications/start-menu.desktop"
chmod 644 "$STAGE/usr/share/applications/start-menu.desktop"

# -- smoke test ----------------------------------------------------------------

# A file the copy missed installs cleanly and fails on first launch, so the
# staged tree is checked before it is packed, with the launcher's own flags
# (-I) plus -B so nothing is written into the stage. Three checks, the first
# two needing nothing but Python and PyYAML, so they run on a build machine
# with no Qt:
#
#   - every import inside the staged packages names a file that was staged;
#   - the example menu is there, and loads with no validation errors;
#   - the modules import: all of them where the system python3 has PyQt6, and
#     otherwise the Qt-free ones (menu, launcher).
command -v python3 >/dev/null 2>&1 || die "python3 not found; it is needed to check the staged files."
python3 -I -B - "$LIB" <<'PY' || die "the staged files failed the smoke test (above); nothing was packaged."
import ast
import importlib
import pathlib
import sys

lib = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(lib))
problems = []


def is_module(path):
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


for package in ("start_menu", "windowchrome"):
    for source in sorted((lib / package).rglob("*.py")):
        where = source.relative_to(lib)
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                base = source.parent
                for _ in range(node.level - 1):
                    base = base.parent
                if node.module:
                    if not is_module(base.joinpath(*node.module.split("."))):
                        problems.append(f"{where}: from {'.' * node.level}{node.module}")
                elif not (base / "__init__.py").is_file():
                    problems.append(f"{where}: from {'.' * node.level} (no package)")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
                for name in names:
                    top = name.split(".")[0]
                    if top in ("start_menu", "windowchrome") and not is_module(lib.joinpath(*name.split("."))):
                        problems.append(f"{where}: import {name}")

data = lib / "start_menu" / "data"
for name in ("example-menu.yaml", "start-menu.png"):
    if not (data / name).is_file():
        problems.append(f"start_menu/data/{name} is missing (__main__ reads it)")

try:
    import yaml  # noqa: F401
except ImportError:
    print("Note: no PyYAML for this python3; the example menu was not loaded.", file=sys.stderr)
else:
    from start_menu.menu import load_menu

    try:
        _, _, errors = load_menu(str(data / "example-menu.yaml"))
    except Exception as exc:
        errors = [repr(exc)]
    problems += [f"example-menu.yaml: {error}" for error in errors]

try:
    import PyQt6.QtWidgets  # noqa: F401
    modules = [p.stem for p in (lib / "start_menu").glob("*.py") if p.stem != "__init__"]
    scope = "every module"
except ImportError:
    modules = ["menu", "launcher"]
    scope = "the Qt-free modules (no PyQt6 for this python3)"
for name in sorted(modules):
    try:
        importlib.import_module(f"start_menu.{name}")
    except Exception as exc:
        problems.append(f"import start_menu.{name}: {exc!r}")

if problems:
    print("\n".join(problems), file=sys.stderr)
    sys.exit(1)
print(f"Smoke test passed: imports resolve, the example menu loads, {scope} import.")
PY

# -- package metadata --------------------------------------------------------

# Compiled as root at install time, since a user running Start Menu can't write
# __pycache__ under /usr/lib; without it every launch compiles in memory.
# The two cache refreshes are what make the icon and the menu entry appear
# without a logout; both are absent on a bare system and harmless when they are.
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  python3 -m compileall -q /usr/lib/start-menu >/dev/null 2>&1 || true
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
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

# The icon is gone by now, so the cache has to be rebuilt again or the desktop
# keeps showing it in menus until something else refreshes it.
cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm"

INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)"

# A terminal emulator is needed by the 'terminal' and 'hold' launch modes and
# tmux by the 'tmux' mode, but neither is a hard dependency: launcher.py checks
# for them and explains itself in a dialog, so a machine that never uses those
# modes has no reason to carry them.
#
# libqt6svg6 *is* a hard dependency, for a reason that is not obvious: it
# carries Qt's SVG image-format plugin, and without it Qt cannot read an icon
# file that a desktop theme ships only as .svg. Yaru keeps its arrows that way
# (scalable/actions/go-up-symbolic.svg and friends), so on a machine with only
# python3-pyqt6 installed, QIcon.fromTheme("go-previous") and every arrow
# QStyle.standardIcon() resolves through the theme comes back *empty* — the
# window then falls back to Qt's own built-in arrow art and quietly stops
# matching the rest of the desktop. apt does not pull this in on its own:
# python3-pyqt6 does not depend on it.
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.11), python3-pyqt6, python3-yaml, libqt6svg6
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
