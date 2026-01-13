#!/usr/bin/env python3
"""
Linux Start Menu - A GTK-based script launcher
Scans the scripts/ folder and builds native popup menus from the folder structure
"""

import os
import subprocess
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_FOLDER = os.path.join(SCRIPT_DIR, "scripts")

# CSS for menu styling
CSS = b"""
menu menuitem {
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 12px;
    padding-right: 12px;
}
menu menuitem label {
    padding-top: 4px;
    padding-bottom: 4px;
}
"""


def apply_css():
    """Apply custom CSS styling to menus"""
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def clean_display_name(filename):
    """Remove common extensions for cleaner display"""
    name = filename
    for ext in ['.sh', '.bash', '.py', '.pl', '.rb']:
        if name.endswith(ext):
            name = name[:-len(ext)]
            break
    # Also remove leading underscore if present
    if name.startswith('_'):
        name = name[1:]
    return name


def needs_terminal(script_path):
    """Check if script has Terminal=true in the first 10 lines"""
    try:
        with open(script_path, 'r') as f:
            for i, line in enumerate(f):
                if i >= 10:
                    break
                # Look for Terminal=true (case-insensitive)
                if 'terminal=true' in line.lower().replace(' ', ''):
                    return True
    except (IOError, UnicodeDecodeError):
        pass
    return False


def run_script(menu_item, script_path):
    """Execute the selected script"""
    
    # Check if script wants a visible terminal
    if needs_terminal(script_path):
        subprocess.Popen(
            ['gnome-terminal', '--', 'bash', '-c', f'"{script_path}"; exec bash'],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        # Detach the subprocess completely so it outlives this script
        if os.access(script_path, os.X_OK):
            subprocess.Popen(
                [script_path],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                ['bash', script_path],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    Gtk.main_quit()


def build_menu(directory):
    """Recursively build a Gtk.Menu from a directory structure"""
    menu = Gtk.Menu()
    
    try:
        items = sorted(os.listdir(directory))
    except PermissionError:
        return menu
    
    # Separate folders and files, process folders first
    folders = []
    files = []
    
    for item_name in items:
        if item_name.startswith('.'):
            continue
        
        item_path = os.path.join(directory, item_name)
        
        if os.path.isdir(item_path):
            folders.append((item_name, item_path))
        elif os.path.isfile(item_path):
            files.append((item_name, item_path))
    
    # Add folders as submenus
    for name, path in folders:
        menu_item = Gtk.MenuItem(label=name)
        submenu = build_menu(path)
        menu_item.set_submenu(submenu)
        menu.append(menu_item)
    
    # Add separator if we have both folders and files
    if folders and files:
        menu.append(Gtk.SeparatorMenuItem())
    
    # Add files as executable items
    for name, path in files:
        display_name = clean_display_name(name)
        menu_item = Gtk.MenuItem(label=display_name)
        menu_item.connect('activate', run_script, path)
        menu.append(menu_item)
    
    menu.show_all()
    return menu


def on_menu_deactivate(menu):
    """Called when menu closes (click outside, Escape, etc.)"""
    Gtk.main_quit()


def main():
    if not os.path.isdir(SCRIPTS_FOLDER):
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=f"Scripts folder not found:\n{SCRIPTS_FOLDER}"
        )
        dialog.run()
        dialog.destroy()
        return
    
    # Apply custom styling
    apply_css()
    
    # Build the menu
    menu = build_menu(SCRIPTS_FOLDER)
    menu.connect('deactivate', on_menu_deactivate)
    
    # Get current mouse position
    display = Gdk.Display.get_default()
    seat = display.get_default_seat()
    pointer = seat.get_pointer()
    screen, mouse_x, mouse_y = pointer.get_position()
    
    # Create a tiny invisible window at the cursor position
    win = Gtk.Window(type=Gtk.WindowType.POPUP)
    win.set_default_size(1, 1)
    win.move(mouse_x, mouse_y)
    win.show_all()
    
    # Ensure window is realized before popup
    while Gtk.events_pending():
        Gtk.main_iteration()
    
    # Get the Gdk window and create a rectangle at origin
    gdk_win = win.get_window()
    rect = Gdk.Rectangle()
    rect.x = 0
    rect.y = 0
    rect.width = 1
    rect.height = 1
    
    # Popup the menu at the rectangle
    menu.popup_at_rect(gdk_win, rect, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.NORTH_WEST, None)
    
    # Run GTK main loop
    Gtk.main()
    
    # Clean up
    win.destroy()


if __name__ == '__main__':
    main()
