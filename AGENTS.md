# Notes to AI Agents

## What this is

PyCommander is a PyQt6 desktop app: a keyboard-driven menu for launching
scripts and commands. The entire menu is one YAML file (`menu.yaml`, path
given as a CLI arg — see `README.md`); the whole interaction is four keys:
**↑↓** to move, **→** to open a section, **←** to go back, **⏎** to launch.
One level is shown at a time — going into a section replaces the list rather
than expanding it — so the menu stays the same size no matter how deep it
gets. It's a rewrite of an older curses-based `Commander` tool, but here the
tree, display names, launch modes and icons are explicit YAML properties
instead of being encoded in filenames.

A menu item is one of three things: a **section** (`items:`, nests further
items), a **script file** (`file:`, a path on disk), or an inline **`sh:`**
snippet. Each script has a launch mode — `detached` (no window), `terminal`
(window closes on exit), `hold` (window stays open until Enter), or `tmux`
(window attaches to a named tmux session that outlives it, so closing the
window only detaches). `tmux` is the only mode
with a required extra property (`tmux_session:`) and an external dependency.

## Architecture / top-level GUI

- `pycommander/__main__.py` — entry point: argparse, `QApplication`, startup
  validation, creates a starter `menu.yaml` if the given path doesn't exist.
- `pycommander/menu.py` — the model: YAML in, a tree of `MenuNode` out, with
  full validation (all errors collected and reported at once) and the
  reverse `dump_menu()` for saving edits back out.
- `pycommander/launcher.py` — turns a `MenuNode` into a spawned process for
  each of the four launch modes, detached from PyCommander's own session.
  `tmux` mode wraps the command it would otherwise have run in a generated
  shell script that creates or reattaches to the session; its session-name
  and tmux-installed checks happen in Python first, so the failures that
  actually happen are dialogs rather than a terminal window that opens and
  immediately dies. The same reasoning puts `tmux_session_state()` in Python:
  when the session is already live, `launch()` calls back through its
  `on_running_session` hook to ask attach/restart/cancel, and only then
  decides whether to open a window at all. The hook keeps the launcher free
  of Qt — `window.py` supplies the actual dialog. Note that tmux's `=`
  exact-match target prefix works for `has-session`, `list-panes`,
  `kill-session` and `attach-session` but **not** for `set-option`,
  `display-message` or `capture-pane`, which is why the wrapper mixes the two
  forms.
- `pycommander/window.py` — the GUI: `MainWindow` (header showing the
  current breadcrumb, the `MenuTreeView`, an **Edit** toggle switch + footer
  hint bar) and `MenuTreeView` itself, a `QTreeView`/`QStandardItemModel`
  that shows one level at a time via `setRootIndex()` rather than expanding.
  When **Edit** is on, a toolbar (**New Folder** / **New Item** buttons)
  appears and each row grows right-justified action icons (move up/down,
  edit, delete).
- `pycommander/dialogs/` — the two editing dialogs opened from those action
  icons, one per module: `folder_name.py` (`FolderNameDialog` — rename/create
  a section) and `item_edit.py` (`ItemEditDialog` — name, file-or-inline-`sh`,
  working directory, launch mode and — shown only for `tmux` mode — the
  session name, for a script), over a shared `style.py` holding the bordered
  frame and lightened-input styling both of them draw. The package's
  `__init__.py` re-exports both classes, so `window.py` imports them from
  `.dialogs` without naming a module.

Every edit made through the GUI does a full save-and-reload round trip:
write the in-memory tree to `menu.yaml`, then re-run it back through the
same `load_menu()` validation startup uses, so the GUI always matches what's
actually on disk.

See `README.md` for the full menu-file reference and key list, and
`USER_GUIDE.md` for end-user-facing documentation.

## Working in this repo

* Do not commit changes to 'git' repository, or offer to. Only the Human
  developer will do commits.
