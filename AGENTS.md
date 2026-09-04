# Notes to AI Agents

## What this is

Start Menu is a PyQt6 desktop app: a keyboard-driven menu for launching scripts and commands. The entire menu is one YAML file (`menu.yaml`, path given as a CLI arg — see `README.md`); the whole interaction is four keys: **↑↓** to move, **→** to open a section, **←** to go back, **⏎** to launch. One level is shown at a time — going into a section replaces the list rather than expanding it — so the menu stays the same size no matter how deep it gets.

A menu item is one of three things: a **section** (`items:`, nests further items), a **script file** (`file:`, a path on disk), or an inline **`sh:`** snippet. Each script has a launch mode — `detached` (no window), `terminal` (window closes on exit), `hold` (window stays open until Enter), or `tmux` (window attaches to a named tmux session that outlives it, so closing the window only detaches). `tmux` is the only mode with a required extra property (`tmux_session:`) and an external dependency.

## Architecture / top-level GUI

- `start_menu/__main__.py` — entry point: argparse, `QApplication`, startup validation, creates a starter `menu.yaml` if the given path doesn't exist. Also the two `windowchrome` setup calls, which are order-sensitive — see the window-chrome entry below.
- `start_menu/menu.py` — the model: YAML in, a tree of `MenuNode` out, with full validation (all errors collected and reported at once) and the reverse `dump_menu()` for saving edits back out.
- `start_menu/launcher.py` — turns a `MenuNode` into a spawned process for each of the four launch modes, detached from Start Menu's own session. `tmux` mode wraps the command it would otherwise have run in a generated shell script that creates or reattaches to the session; its session-name and tmux-installed checks happen in Python first, so the failures that actually happen are dialogs rather than a terminal window that opens and immediately dies. The same reasoning puts `tmux_session_state()` in Python: when the session is already live, `launch()` calls back through its `on_running_session` hook to ask attach/restart/cancel, and only then decides whether to open a window at all. The hook keeps the launcher free of Qt — `window.py` supplies the actual dialog. Note that tmux's `=` exact-match target prefix works for `has-session`, `list-panes`, `kill-session` and `attach-session` but **not** for `set-option`, `display-message` or `capture-pane`, which is why the wrapper mixes the two forms.
- `start_menu/window.py` — the GUI: `MainWindow` (header showing a back arrow button + the current breadcrumb — the whole bar hidden at the top level, where there's nothing to show and nowhere to back up to — the `MenuTreeView`, an **Edit** toggle switch + footer hint bar) and `MenuTreeView` itself, a `QTreeView`/`QStandardItemModel` that shows one level at a time via `setRootIndex()` rather than expanding. When **Edit** is on, a toolbar appears (**New Folder** / **New Item**, plus **Cut** / **Undo Cut** / **Paste**, each shown only when it applies), rows become multi-selectable, and each row grows right-justified action icons (move up/down, edit, delete). Cut/paste moves *items* between folders — folders themselves are deliberately not cuttable, which is why `_handle_cut` rejects a selection containing one instead of silently skipping it. A cut writes nothing: the nodes stay in the tree and their rows are merely hidden (`setRowHidden`, not left out of the model, so the row-number ↔ `MenuNode` mapping the other edit paths rely on still holds), and the move only becomes real on **Paste**. Because a save-and-reload builds all-new `MenuNode` objects, any *other* edit while a cut is pending drops the cut — nothing is lost, since the items were never removed.
- `start_menu/dialogs/` — the two editing dialogs opened from those action icons, one per module: `folder_name.py` (`FolderNameDialog` — rename/create a section) and `item_edit.py` (`ItemEditDialog` — name, file-or-inline-`sh`, working directory, launch mode and — shown only for `tmux` mode — the session name, for a script), over a shared `style.py` holding the bordered frame and lightened-input styling both of them draw. The package's `__init__.py` re-exports both classes, so `window.py` imports them from `.dialogs` without naming a module.

Every edit made through the GUI does a full save-and-reload round trip: write the in-memory tree to `menu.yaml`, then re-run it back through the same `load_menu()` validation startup uses, so the GUI always matches what's actually on disk.

See `README.md` for the full menu-file reference and key list, and `docs/USER_GUIDE.md` for end-user-facing documentation.

## Things that will bite you

- **The window chrome lives in `windowchrome`, not here — read `../windowchrome/README.md` before touching any of it.** The colored title bar — and with it the thin frame the decoration draws down the sides and along the bottom — is a sibling library (`[tool.uv.sources]` in `pyproject.toml` points at `../windowchrome`, editable, so an edit there is live here with no reinstall; the checkout has to *be* a sibling or `uv run` fails outright). Its README carries the whole of what was measured: that the bar is colorable only on Wayland and only by repurposing three application palette roles; that `libadwaita.so` links no `QPalette` symbol at all while `bradient` does, which is what `QT_WAYLAND_DECORATION` is choosing between; that the decoration's `QMargins{3, 30, 3, 3}` are compiled-in constants, so neither the bar's height nor the frame's 3px is adjustable; and that giving a widget a stylesheet severs its palette inheritance, which is why an application event filter hands the body colors back. That last one is not hypothetical here — `MenuTreeView` styles itself, and so does every label, button and input field in the app.

  What this app owes it, and what will break if it is forgotten: `windowchrome.configure(START_MENU_THEME)` **before** `QApplication` and `windowchrome.install(app)` **after** it — both in `__main__`, and both order-sensitive, the first because the decoration plugin is chosen by an environment variable read inside that constructor. That is the whole integration: two calls, and nothing about any window's layout changes. The dialogs keep the gray `dialogFrame` QFrame they always had.

  `START_MENU_THEME` is in `start_menu/__init__.py`, beside `APP_NAME` and `UI_POINT_SIZE`. It matches the other apps here deliberately.

  Nothing in this app derives a color from the palette's `Window` or `WindowText` roles, so the `body_window_color()` / `body_text_color()` rule the library states costs nothing here — the one palette read in the codebase is `dialogs/style.py`'s, and it reads `Base`, which the title bar never touches. Keep it that way: a new color derived from `Window` would come out tinted with the title bar blue.

  `QMessageBox` deliberately calls none of this and keeps the title bar's colors, being transient.

  The library briefly also painted a thicker border just inside every window (`bordered_body()`), which replaced the dialogs' own gray frame. It was removed: the decoration's own 3px frame, which takes the title bar's color for free, is what the design wants. Do not reintroduce it.

## Working in this repo

* Do not commit changes to 'git' repository, or offer to. Only the Human developer will do commits.
