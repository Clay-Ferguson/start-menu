# Linux Start Menu

A lightweight GTK-based start menu for Linux that launches shell scripts from a customizable folder structure.

## Overview

This project provides a native popup menu that appears at your cursor position, built dynamically from the contents of the `scripts/` folder. Simply organize your scripts into folders, and the menu structure mirrors your file system hierarchy.

## Requirements

- Python 3
- GTK 3 (via PyGObject)
- `gnome-terminal` (for scripts that require a visible terminal)

Install dependencies on Debian/Ubuntu:
```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gnome-terminal
```

## Usage

Run the menu:
```bash
./start-menu.py
```

Optionally, specify a different scripts folder:
```bash
./start-menu.py myfolder
```

The folder name is relative to the script's location. If no argument is provided, it defaults to `scripts/`.

The menu will pop up at your current mouse position. Click a script to run it, or click outside / press Escape to dismiss.

## Defining the Menu Structure

The menu is built entirely from the `scripts/` folder. **Your folder structure becomes your menu structure:** To see this work, simply put some bash script files in the 'scripts' folder (or any subfolders onder 'scripts' to see it working)

### Rules:
- **Folders** become submenus
- **Files** become clickable menu items
- **File extensions** (`.sh`, `.bash`, `.py`, `.pl`, `.rb`) are hidden in the menu display
- **Leading underscores** in filenames are stripped from the display name (useful for ordering)
- **Hidden files** (starting with `.`) are ignored
- Folders appear first, followed by a separator, then files (both sorted alphabetically)

## Supported File Types

### Shell Scripts
Place any executable script in the `scripts/` folder. If a script is not marked executable, it will be run with `bash`.

### File Links (Shortcuts)
Symbolic links are fully supported. Create symlinks to scripts located elsewhere on your system:
```bash
ln -s /path/to/your/script.sh scripts/My\ Script.sh
```

This allows you to include scripts without moving them from their original location.

## Terminal=true Feature

By default, scripts run silently in the background with no visible output. If you need to see the output or interact with a script, add the following comment anywhere in the **first 10 lines** of your script:

```bash
#!/bin/bash
# Terminal=true

echo "This will be visible in a terminal window!"
read -p "Press Enter to continue..."
```

When `Terminal=true` is detected (case-insensitive, spaces ignored), the script will launch in a new `gnome-terminal` window that stays open after the script completes.

**Working Directory:** When running in a terminal, the working directory is automatically set to the folder containing the script. If the script is a symbolic link, the working directory will be the folder containing the actual target file, not the link itself.

**Use cases:**
- Scripts that require user input
- Scripts with important output to review
- Interactive tools and utilities

## Desktop Icon Launcher

The included `Menu.desktop` file demonstrates how to launch the menu from a desktop icon or application launcher.

Example `.desktop` file:
```ini
[Desktop Entry]
Name=Start Menu
Comment=Script Launcher Menu
Exec=/path/to/start-menu.py
Icon=application-x-executable
Terminal=false
Type=Application
Categories=Utility;
```

To install:
1. Edit `Menu.desktop` and update the `Exec=` path to your installation location
2. Copy to your desktop or applications folder:
   ```bash
   cp Menu.desktop ~/.local/share/applications/
   ```
3. You can also assign a keyboard shortcut to the `Exec` command in your desktop environment settings

## Quick Install for GNOME/Ubuntu

For GNOME/Ubuntu users, you can automatically install Start Menu to your dock with a single command:

```bash
./install.sh
```

This will:
- Create a `.desktop` file with the correct paths
- Add Start Menu to your dock for single-click launching
- Set up the custom icon

To remove Start Menu from the dock and applications menu:

```bash
./uninstall.sh
```

Note: The uninstall script only removes the desktop integration—your source files remain intact.

## Tips

- **Quick access**: Bind `start-menu.py` to a keyboard shortcut or mouse gesture for instant access
- **Organization**: Use folders to group related scripts (e.g., "Development", "System", "Media")
- **Naming**: Use descriptive filenames since they become menu labels
- **Ordering**: Prefix files with `_` to influence sort order while keeping clean display names


