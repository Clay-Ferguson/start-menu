# Notes to AI Agents

## What this is

Start Menu is a PyQt6 desktop app: a keyboard-driven menu for launching scripts and commands. The entire menu is one YAML file (path given as an optional CLI arg, defaulting to `~/.config/start-menu/menu.yaml`); the whole interaction is four keys: **↑↓** to move, **→** to open a section, **←** to go back, **⏎** to launch. One level is shown at a time — going into a section replaces the list rather than expanding it — so the menu stays the same size no matter how deep it gets.

A menu item is one of three things: a **section** (`items:`, nests further items), a **script file** (`file:`, a path on disk), or an inline **`sh:`** snippet. Each script has a launch mode — `detached` (no window), `terminal` (window closes on exit), `hold` (window stays open until Enter), or `tmux` (window attaches to a named tmux session that outlives it, so closing the window only detaches). `tmux` is the only mode with a required extra property (`tmux_session:`) and an external dependency.

The modules are heavily commented, and the comments record *why*. Read the comments at a site before "simplifying" it. See `README.md` for the full menu-file reference and key list, and `docs/USER_GUIDE.md` for end-user documentation.

## Running

```bash
./start.sh [MENU_FILE]
./lint.sh
```

`start.sh` runs through `uv`; `pyproject.toml` sets `package = false`, so there is no install step and edits are live. `windowchrome` is a **sibling checkout** (`[tool.uv.sources]` → `../windowchrome`, editable) — it must exist or `uv run` fails. There is deliberately no automated test suite; `./lint.sh` (ruff, pyright, `bash -n`) must stay clean.

The menu path is optional because the packaged desktop entry relies on the default: one `Exec=` line has to serve every user on the machine. A path that doesn't exist yet is created by byte-copying `start_menu/data/example-menu.yaml` (not round-tripped through `dump_menu`, which would strip its comments). Startup failures are `QMessageBox`es, not stderr, because the app is launched from a desktop icon.

Installed from the `.deb` it is `start-menu`, running `/usr/lib/start-menu` under `python3 -I`, so neither `PYTHONPATH` nor pip user installs can shadow the distribution's PyQt6. The Debian package is `start-menu`; the Python package is `start_menu` — hyphen in paths, underscore in imports.

## Layout

Top level: `start_menu/` (the app), `docs/` (the User Guide and its screenshots; not shipped), `packaging/` (`build-deb.sh`, the `.desktop` template, and `icons/` with `source.png`, `make-icons.py` and the generated hicolor PNGs), `start.sh` and `lint.sh`. Tool settings live in `ruff.toml` and `pyrightconfig.json`, so `pyproject.toml` stays the runtime dependency list. The package:

- `__main__.py` — entry point: argparse, `QApplication`, the `sys.excepthook` that turns an escaped exception into a dialog, seeding a missing menu file, startup validation.
- `menu.py` — the model: YAML in, a tree of `MenuNode` out, with full validation (all errors collected and reported at once, `format_errors()` for the dialog), `dump_menu()` for saving (atomic: temp file + `os.replace`, symlinks followed), and the pure tree edits the window uses — `nodes_at()`, `detach_node()` — plus `resolve_file()` and `TMUX_SESSION_CHARS`. No Qt.
- `launcher.py` — turns a `MenuNode` into a spawned process for each launch mode, detached from Start Menu's own session, and `open_in_editor()`. No Qt: when a tmux session is already live, `launch()` asks through its `on_running_session` hook, and `window.py` supplies the dialog.
- `window.py` — `MainWindow`: header (back arrow + breadcrumb, hidden at the top level), edit toolbar, the **Edit** switch and footer hints; and everything that changes the menu or asks the user something — launching, the tmux attach/restart question, edit/delete/move, new folder/item, cut/paste, and `_save_and_reload()`.
- `tree.py` — `MenuTreeView` (a `QTreeView` over a `QStandardItemModel` that shows one level at a time via `setRootIndex()`), `RowActionDelegate` (the per-row action icons), tooltips. A pure view: it reports what was asked for through signals (`launch_requested`, `edit_requested`, …) and never launches or edits anything itself.
- `icons.py` — `at_size()`, `edit_icon()`, `back_icon()`, and the drawn-glyph fallback when no theme has an icon.
- `style.py` — shared look: `HIGHLIGHT_BG`/`HIGHLIGHT_FG`/`HOVER_BG`, and the dialogs' `field_background()`/`field_border()`/`field_style()`. Imports nothing from the package except `UI_POINT_SIZE`.
- `folder_dialog.py` — `FolderNameDialog`, renaming or creating a section.
- `item_dialog.py` — `ItemEditDialog`: takes a `MenuNode` (None for a new one), and `edited_item()` returns a new `MenuNode` (carrying over the `icon:` it doesn't edit). A field added to `MenuNode` is added here and needs no plumbing in between.
- `data/` — `example-menu.yaml` (the seed for a new menu file) and `start-menu.png` (the window icon, which a checkout run needs because no desktop entry supplies one). Found through `__main__.DATA_DIR`.

## Rules

- **Only the widget modules import Qt.** `menu` and `launcher` are plain Python; the `.deb`'s smoke test imports them on a build machine with no PyQt6.
- **Every GUI edit is a full save-and-reload round trip**: mutate `self.nodes`, then `_save_and_reload()` writes the file and re-runs it through the same `load_menu()` validation startup uses, so the GUI always matches what's on disk. No path out of `_save_and_reload()` may leave the view and `self.nodes` disagreeing — the view maps rows to nodes by **row number**, and a mismatch aims the next edit at the wrong item. On a failed write it reloads from disk; if even that fails, it rebuilds from `self.nodes`.
- **The file on disk wins over the in-memory tree.** `MainWindow` remembers the file's mtime; if it changed since (the `e` editor, usually), a GUI edit is not saved — the user is told and the menu reloads from the file.
- **Cut hides, it doesn't remove.** Cut rows are hidden with `setRowHidden` (not left out of the model, which would break the row ↔ node mapping), and the move only becomes real on **Paste**. Any other edit rebuilds every `MenuNode`, so it drops a pending cut — nothing is lost, since the items never left the file. Folders are deliberately not cuttable. Up/down moves skip hidden rows (`MenuTreeView.neighbor_row`).
- **A `cwd:` that is present but YAML-null means `~`.** A bare `~` is YAML's null; the docs and the example write `cwd: ~` and mean home. `dump_menu` writes it back quoted.
- **Don't set `applicationDisplayName`.** Qt appends it to every window title that isn't exactly it, doubling "Start Menu — …" dialog titles. Each window spells out its own title.
- **Do not style the title bar or window frame.** They used to be colored through `windowchrome` (on Wayland: the `bradient` decoration plugin plus repurposed palette roles and an app-wide event filter). That was removed as too fragile — it rested on undocumented plugin internals and leaked into unrelated code. Don't reintroduce it.
- **Shared widget looks live in `windowchrome`** — read `../windowchrome/README.md` before touching any of them. It is editable from here, so an edit there is live with no reinstall. Start Menu takes three things from it, none with any setup call or ordering rule:
  - **Wide scroll bars** — `apply_scrollbars()` on `MenuTreeView` and on the `sh` editor (§9). It reads the palette's `Base`; the `sh` editor is *not* painted in `Base`, so it is handed `field_background()`, or the groove reads as a darker stripe. It goes on the scroll bar children, not the view, which is what lets `_stylesheet()` be re-applied to the view on every edit-mode toggle.
  - **The item dialog's radio buttons** — `apply_radios()` (§10), handed `field_background()` so the unchecked circle matches the fields around it.
  - **The Edit switch** — `ToggleSwitch` (§11), a `QAbstractButton` (so `toggled`/`setChecked()` work as usual), given `on_color=HIGHLIGHT_BG` rather than the system accent.
- **The `.deb` is built by `packaging/build-deb.sh`.** It copies the whole `start_menu/` (including `data/`) and `windowchrome/` trees, installs the hicolor icons, then smoke-tests the stage before packing: every intra-package import resolves to a staged file, the data files exist, the example menu loads with zero errors, and the modules import (only the Qt-free ones when the system python3 has no PyQt6). PyQt6 and PyYAML come from apt; a new third-party dependency needs a Debian package in the script's `Depends:` as well as `pyproject.toml`. Regenerate icons with `uv run --no-project --with pillow packaging/icons/make-icons.py`.
- Do not commit to git, or offer to. Only the human developer commits.

## Qt 6.4 compatibility

The GUI has to look the same on Qt 6.4 as on current Qt, and 6.4 is the older, stricter one. `uv run` builds against current PyQt6 (Qt 6.11 at the time of writing); the `.deb` runs against apt's `python3-pyqt6`, which on Ubuntu 24.04 is bindings 6.6 over **Qt 6.4.2**. Where they disagreed, the fix favors the older one:

- **`libqt6svg6` is a hard runtime dependency, and apt will not pull it in on its own.** It carries Qt's SVG image-format plugin; without it Qt can't read an icon a theme ships only as `.svg`. Yaru keeps its arrows that way, so `QIcon.fromTheme("go-previous")` and every arrow `QStyle.standardIcon()` resolves through the theme come back **empty** and the window falls back to Qt's built-in arrow art. `build-deb.sh` names it in `Depends:`. (`QIcon.setFallbackThemeName()` does *not* substitute for it.)
- **A themed icon is not the size you asked for.** A theme ships a few fixed sizes and Qt hands back the nearest; older Qt won't scale one *up*, so a 32px Yaru folder came back 16px under the `.deb`. `icons.at_size()` pulls the icon at 256px and re-wraps it in a pixmap-backed `QIcon`, which shrinks whatever it's given. Every icon goes through it. It also pins the pixmap as the `Selected` face, because Qt otherwise washes the icon in the palette's `Highlight` (the desktop accent, not `HIGHLIGHT_BG`). `MenuTreeView._icon_cache` keeps one built icon per distinct `icon:` value.
- **A `QTreeView::item` rule needs a `background` for its `padding` to apply.** Qt hands a row to the native style whenever the rule has nothing of its own to draw, and the native painter ignores the rule's padding — which left the indent showing on the selected row only. `_stylesheet()` therefore sets `background: transparent` on the base item rule. That costs the native hover, hence the explicit `::item:hover` rule, which must stay *before* the `:selected` ones (equal specificity, so source order decides).

## tmux behavior that shapes the code

- **Checks happen in Python first** (session name, tmux installed, session already live), so the failures that actually happen are dialogs rather than a terminal window that opens and immediately dies. The generated wrapper repeats the tmux check so a vanished tmux isn't misreported as "the process exited immediately".
- **Session names are exact-matched with the `=` target prefix**, or `llama` would find (and on Restart, kill) `llama-deck`. But `=` works for `has-session`, `list-panes`, `kill-session` and `attach-session`, **not** for `set-option`, `display-message` or `capture-pane` — which is why the wrapper mixes the two forms, and why `tmux_session_started()` matches names from `list-sessions` instead.
- **`remain-on-exit` must be set in the same tmux invocation as `new-session`** (chained with `\;`), or a script that fails in milliseconds takes its error output with it.
- **`$TMUX`/`$TMUX_PANE` are unset** in the wrapper: an inherited value makes tmux refuse to attach, thinking it's nesting.
- **Launched processes get `_child_env()`**, which strips Start Menu's own virtualenv (`VIRTUAL_ENV`, its `bin/` on `PATH`, `PYTHONPATH`, `PYTHONHOME`) so a script's `python` is the system one.
