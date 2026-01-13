#!/bin/bash
# Start Menu Install Script for GNOME/Ubuntu
# Installs Start Menu to the applications menu and adds it to the dock

set -e

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/start-menu.desktop"
APP_ID="start-menu.desktop"

echo "Installing Start Menu..."

# Ensure the applications directory exists
mkdir -p "$HOME/.local/share/applications"

# Generate the .desktop file with the correct path
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Start Menu
Comment=GTK popup menu for launching scripts
Exec=$SCRIPT_DIR/start-menu.py
Icon=$SCRIPT_DIR/start-menu.png
Terminal=false
Type=Application
Categories=Utility;
StartupNotify=false
EOF

echo "Created desktop entry: $DESKTOP_FILE"

# Update the desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$HOME/.local/share/applications/"
    echo "Updated desktop database"
fi

# Add to GNOME dock favorites if not already present
if command -v gsettings &> /dev/null; then
    CURRENT_FAVORITES=$(gsettings get org.gnome.shell favorite-apps)
    
    if [[ "$CURRENT_FAVORITES" != *"'$APP_ID'"* ]]; then
        # Remove the closing bracket, add our app, close the bracket
        NEW_FAVORITES=$(echo "$CURRENT_FAVORITES" | sed "s/]$/, '$APP_ID']/")
        # Handle empty list edge case
        if [[ "$CURRENT_FAVORITES" == "@as []" ]]; then
            NEW_FAVORITES="['$APP_ID']"
        fi
        gsettings set org.gnome.shell favorite-apps "$NEW_FAVORITES"
        echo "Added Start Menu to dock"
    else
        echo "Start Menu is already in the dock"
    fi
else
    echo "Note: gsettings not found - please manually add Start Menu to your dock"
fi

echo ""
echo "Installation complete!"
echo "Start Menu should now appear in your dock for single-click launching."
