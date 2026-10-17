#!/usr/bin/env bash
# Makes the webcam's mic the default microphone (see wireplumber-mic.conf). No password needed.
# Run on the Pi from the repo:  bash system/install_mic.sh
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cp system/wireplumber-mic.conf ~/.config/wireplumber/wireplumber.conf.d/51-carpc-mic.conf
# Forget any microphone picked by hand earlier, so the priorities decide.
sed -i '/^default.configured.audio.source/d' ~/.local/state/wireplumber/default-nodes 2>/dev/null || true
systemctl --user restart wireplumber
sleep 2
echo "Default microphone:"
wpctl inspect @DEFAULT_AUDIO_SOURCE@ 2>/dev/null | grep -E "node.description|node.nick" | head -1 \
    || echo "  none (plug in the webcam)"
