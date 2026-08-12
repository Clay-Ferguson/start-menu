# PyCommander

A keyboard-driven menu for launching scripts. The entire menu lives in one YAML
file, and the whole interaction is four keys: **↑↓** to move, **→** to open a
section, **←** to go back, **⏎** to launch. One level is shown at a time — going
into a section replaces the list rather than expanding it — so the menu stays
the same size no matter how deep it gets. The mouse is never required.

It is a PyQt6 rewrite of [Commander](../../commander), which derived its menu
from a folder of scripts and encoded each script's launch behavior in trailing
underscores on the filename. Here the tree, the display names, the launch modes
and the icons are all explicit YAML properties.

## Running

```bash
./start.sh                    # uses ./menu.yaml
./start.sh --menu other.yaml  # or any other menu file
```

`start.sh` runs the app through [uv](https://docs.astral.sh/uv/), which creates
and refreshes the virtualenv from `pyproject.toml` on every run — there is no
install step and nothing to activate.

`./install.sh` adds a desktop entry so PyCommander shows up in your application
launcher; `./uninstall.sh` removes it.

## Keys

| Key | Action |
|---|---|
| `↑` `↓` | Move the highlight within the current level |
| `→` | Open the highlighted section (no-op on a script) |
| `←` | Back up one level, landing the highlight on the section you came out of |
| `⏎` | Launch the highlighted script, or open the highlighted section |
| `F5` / `Ctrl+R` | Reload `menu.yaml` from disk |
| `Esc` / `q` | Quit |

The window **stays open** after a launch, so you can fire off several things in
a row. Launched scripts run in their own session and survive quitting.

## The menu file

Top-level key `menu:` holds a list of items. An item with `items:` is a
**section**; an item with `file:` is a **script**. Items appear in the order you
write them — there is no sorting.

```yaml
menu:
  - name: Maintenance
    icon: applications-system        # optional
    items:
      - name: backup
        file: /home/clay/ferguson/scripts/backup/backup.sh
        launch: terminal
      - name: status
        file: ~/ferguson/projects/llama-deck/status.sh
        launch: hold

  - name: Lingo Web
    file: /home/clay/ferguson/commander/scripts/Lingo Web.sh
    launch: detached
```

| Key | Applies to | Required | Meaning |
|---|---|---|---|
| `name` | both | yes | The label shown in the menu |
| `items` | section | yes | The child items |
| `file` | script | yes | Path to the shell script. `~` and `$VARS` are expanded and symlinks resolved |
| `launch` | script | no | How to run it (see below). Default `terminal` |
| `cwd` | script | no | Working directory. Defaults to the script's own directory |
| `icon` | both | no | An icon theme name (`utilities-terminal`) or a path to an image file. Defaults to a folder icon for sections, a file icon for scripts |

### Launch modes

| `launch:` | What happens | Use for |
|---|---|---|
| `detached` | No terminal window at all; the script runs fully detached with its output discarded | GUI apps — editors, browsers, anything with its own window |
| `terminal` | A fresh terminal window; the script replaces the shell, so the window closes the instant the script exits | Interactive scripts that prompt for sudo or do their own `read` |
| `hold` | A fresh terminal window that stays open until you press Enter, showing the exit status | Scripts that print a report and exit quickly |

These are the same three behaviors Commander spelled as no suffix, `_`, and
`__` respectively.

Scripts always run under `bash -lc` (a *login* shell), so they see the same
`PATH` and profile they would get from a real terminal rather than the
stripped-down desktop-session environment. A script without the execute bit
still runs — it just gets an explicit `bash` in front of it.

For `terminal` and `hold`, the first available terminal emulator is used, in
this order: `gnome-terminal`, `konsole`, `xfce4-terminal`,
`x-terminal-emulator`, `xterm`.

### Errors

The menu file is validated on load. Every problem found is reported at once,
each tagged with the offending item's location:

```
menu.yaml has 2 problem(s):

  • menu[2].items[1] (status): unknown launch mode 'bogus'; expected one of detached, hold, terminal.
  • menu[4] (Lingo Web): has both 'items:' and 'file:' — an item is either a section (items) or a script (file), not both.
```

On startup that's fatal. On `F5` the previous menu stays loaded, so you can fix
the file and hit `F5` again.

Missing script files are *not* an error at load time — a path may live on a
drive that isn't mounted yet. You get a dialog if you try to launch one.

## Layout

```
start.sh              launcher (uv run python -m pycommander)
menu.yaml             the menu
pycommander/
  __main__.py         argparse, QApplication, startup validation
  menu.py             YAML -> MenuNode tree, with validation
  launcher.py         the three launch modes
  window.py           MenuTreeView (the navigation) + MainWindow
```

The tree is a real `QTreeView` over a `QStandardItemModel`; showing one level at
a time is `setRootIndex()` rather than expanding, which is why per-item icons
and everything else native comes for free.
