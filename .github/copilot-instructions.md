# Copilot Instructions for `Start Menu`

## Project Overview

`Start Menu` is a GTK3-based popup start menu for Linux that dynamically builds menus from a `scripts/` folder structure. The main entry point is [start-menu.py](../start-menu.py).

## Architecture

- **Single-file application**: All menu logic lives in `start-menu.py` (~200 lines)
- **Convention-over-configuration**: The `scripts/` folder hierarchy *is* the menu structure—no config files
- **Fire-and-forget execution**: Scripts launch detached from the menu process via `subprocess.Popen` with `start_new_session=True`

## Script Conventions

### Folder/File → Menu Mapping
```
scripts/
  Backup/           → Submenu "Backup"
    backup-ferguson.sh  → Menu item "backup-ferguson"
    pick-pass.sh     → Menu item "pick-pass" (underscore stripped)
```

- Folders become submenus, files become clickable items
- Extensions `.sh`, `.bash`, `.py`, `.pl`, `.rb` are stripped from display names
- Leading underscores (`_`) are stripped (useful for sort ordering)
- Hidden files (`.` prefix) are ignored

### Terminal=true Directive
Add `# Terminal=true` in the **first 10 lines** of any script to run it in a visible `gnome-terminal` window:

```bash
#!/bin/bash
# Terminal=true
echo "Interactive output visible here"
```

Scripts without this directive run silently in the background.

## Key Functions in start-menu.py

| Function | Purpose |
|----------|---------|
| `build_menu(directory)` | Recursively builds `Gtk.Menu` from folder structure |
| `run_script(menu_item, script_path)` | Executes script (handles Terminal=true detection) |
| `needs_terminal(script_path)` | Scans first 10 lines for `terminal=true` |

## When Adding New Scripts

1. Place executable scripts in `scripts/` or any subfolder
2. Use folders to organize into submenus
3. Prefix with `_` to control sort order without affecting display name
4. Add `# Terminal=true` if the script needs user interaction or visible output
5. Scripts don't need to be executable—non-executable `.sh` files run via `bash`

## Dependencies

- Python 3 with PyGObject (`python3-gi`)
- GTK 3 (`gir1.2-gtk-3.0`)
- `gnome-terminal` (only for `Terminal=true` scripts)

## Running

```bash
./start-menu.py
```

Optionally, specify a different scripts folder:
```bash
./start-menu.py myfolder
```

The folder name is relative to the script's location. If no argument is provided, it defaults to `scripts/`.

The menu appears at the current mouse cursor position. Typically bound to a keyboard shortcut or launched from `Menu.desktop`.
