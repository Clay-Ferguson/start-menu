#!/bin/bash
# Start Menu Uninstall Script for GNOME/Ubuntu
# Removes Start Menu from the dock and applications menu

set -e

DESKTOP_FILE="$HOME/.local/share/applications/start-menu.desktop"
APP_ID="start-menu.desktop"

echo "Uninstalling Start Menu..."

# Remove from GNOME dock favorites
if command -v gsettings &> /dev/null; then
    CURRENT_FAVORITES=$(gsettings get org.gnome.shell favorite-apps)
    
    if [[ "$CURRENT_FAVORITES" == *"'$APP_ID'"* ]]; then
        # Remove our app from the list (handle both middle and end positions)
        NEW_FAVORITES=$(echo "$CURRENT_FAVORITES" | sed "s/, '$APP_ID'//g" | sed "s/'$APP_ID', //g" | sed "s/'$APP_ID'//g")
        gsettings set org.gnome.shell favorite-apps "$NEW_FAVORITES"
        echo "Removed Start Menu from dock"
    else
        echo "Start Menu was not in the dock"
    fi
fi

# Remove the desktop file
if [[ -f "$DESKTOP_FILE" ]]; then
    rm "$DESKTOP_FILE"
    echo "Removed desktop entry: $DESKTOP_FILE"
else
    echo "Desktop entry not found (already removed?)"
fi

# Update the desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications/"
    echo "Updated desktop database"
fi

echo ""
echo "Uninstall complete!"
echo "Note: The Start Menu source files have not been removed."
