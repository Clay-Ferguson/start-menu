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
| `e` | Open `menu.yaml` itself in your editor |
| `Esc` / `q` | Quit |

The window **stays open** after a launch, so you can fire off several things in
a row. Launched scripts run in their own session and survive quitting.

## The menu file

Two top-level keys: `options:` for settings, `menu:` for the menu itself.

```yaml
options:
  editor: code
```

| Setting | Meaning |
|---|---|
| `editor` | What `e` opens the menu file with. A shell command, so it can carry arguments (`code -n`). Defaults to `$VISUAL`, then `$EDITOR`, then `xdg-open`. A GUI editor is assumed — it is launched detached, with no terminal window, so a terminal editor like `vim` would have nowhere to draw |

`menu:` holds a list of items. Every item is exactly one of three
things, decided by which key it carries: `items:` makes it a **section**,
`file:` a **script on disk**, and `sh:` an **inline snippet**. Items appear in
the order you write them — there is no sorting.

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

  - name: Disk report                # inline: no script file needed
    launch: hold
    sh: |
      echo "Free space:"
      df -h /
      docker ps --format '{{.Names}}'

  - name: Lingo Web
    file: /home/clay/ferguson/commander/scripts/Lingo Web.sh
    launch: detached
```

| Key | Applies to | Required | Meaning |
|---|---|---|---|
| `name` | all | yes | The label shown in the menu |
| `items` | section | yes | The child items |
| `file` | script | one of | Path to a shell script. `~` and `$VARS` are expanded and symlinks resolved |
| `sh` | script | `file`/`sh` | Shell commands written inline, one line or many |
| `launch` | script | no | How to run it (see below). Default `terminal` |
| `cwd` | script | no | Working directory. Defaults to the script's own directory for `file:`, to `$HOME` for `sh:` |
| `icon` | all | no | An icon theme name (`utilities-terminal`) or a path to an image file. Defaults to a folder icon for sections, a file icon for scripts |

### Inline `sh:` snippets

Use YAML's `|` block scalar for anything longer than one line — it preserves
newlines exactly. (`>` folds them into spaces, which is almost never what you
want for shell code.) There is no temp file involved: the snippet is handed
straight to `bash -lc` as a whole program, and the shell running it *is* the
terminal's only process, so all three `launch:` modes behave exactly as they do
for a real script file.

Two things to know:

- **It is bash, not a shebang.** A `#!/usr/bin/env python3` first line is just a
  comment; the body always runs under bash. And no flags are set for you — if
  you want `set -euo pipefail`, write it as the first line, the same as you
  would in a real script.
- **Error line numbers are off by one.** Bash counts from the start of the
  program it was handed, and line 1 is the `cd` that puts you in `cwd`, so a
  failure on your snippet's line 3 reports as `bash: line 4:`.

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
still runs — it just gets an explicit `bash` in front of it. An `sh:` snippet
under `hold` runs parenthesised, so a bare `exit` in it ends the snippet rather
than the window, and you still get the exit status and the pause.

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

Any of them is fatal: fix the file and start PyCommander again. There is no
reload — editing the menu means restarting, which takes about as long.

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
