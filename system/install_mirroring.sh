#!/usr/bin/env bash
# Set up live traffic (phone mirroring) on the Pi. Run on the Pi from the repo:
#   bash system/install_mirroring.sh
# scrcpy itself comes from Debian's trixie-backports and needs your password once:
#   echo 'deb http://deb.debian.org/debian trixie-backports main contrib' | sudo tee /etc/apt/sources.list.d/trixie-backports.list
#   sudo apt update && sudo apt install -y -t trixie-backports scrcpy
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
rc=~/.config/labwc/rc.xml
mkdir -p ~/.config/labwc
[ -f "$rc" ] || printf '<?xml version="1.0"?>\n<openbox_config xmlns="http://openbox.org/3.4/rc">\n</openbox_config>\n' > "$rc"

# Keep the mirrored map above the head unit's window (the window manager would otherwise raise the
# head unit over it whenever the status bar or rail is tapped).
if ! grep -q 'title="Live traffic"' "$rc"; then
    cp "$rc" "$rc.before-carpc"
    rules="$(cat "$here/labwc-rules.xml")"
    awk -v rules="$rules" '/<\/openbox_config>|<\/labwc_config>/ { print rules } { print }' "$rc.before-carpc" > "$rc"
fi
# Pass real multi-touch through to the mirror (so pinch-to-zoom works) instead of turning the
# touchscreen into a single mouse pointer. The head unit app reads the touchscreen directly either way.
sed -i 's/mouseEmulation="yes"/mouseEmulation="no"/' "$rc"

kill -HUP "$(pgrep -u "$(id -u)" -x labwc)" 2>/dev/null || true  # reload the window manager's settings
echo "Mirroring settings installed in $rc"
