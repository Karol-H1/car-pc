#!/usr/bin/env bash
# Make the head unit open by itself when the Pi boots to its desktop. No sudo needed.
# Run on the Pi from the repo:  bash system/install_autostart.sh
# Undo:                         rm ~/.config/autostart/carpc.desktop
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/carpc.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Car PC head unit
Exec=bash $here/start_headunit.sh
X-GNOME-Autostart-enabled=true
EOF
echo "Autostart installed: ~/.config/autostart/carpc.desktop"
