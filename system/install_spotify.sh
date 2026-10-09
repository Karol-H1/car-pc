#!/usr/bin/env bash
# Install go-librespot (Spotify Connect) on the Pi as a user service. No sudo needed.
# Run on the Pi from the repo:  bash system/install_spotify.sh
set -euo pipefail

VERSION=v0.10.3
here="$(cd "$(dirname "$0")" && pwd)"

mkdir -p ~/.local/bin ~/.config/go-librespot ~/.config/systemd/user
curl -sL "https://github.com/devgianlu/go-librespot/releases/download/$VERSION/go-librespot_linux_arm64.tar.gz" \
    | tar xz -C ~/.local/bin go-librespot
cp "$here/go-librespot/config.yml" ~/.config/go-librespot/config.yml
cp "$here/go-librespot.service" ~/.config/systemd/user/go-librespot.service

systemctl --user daemon-reload
systemctl --user enable --now go-librespot
systemctl --user restart go-librespot  # pick up a changed config on reinstall
echo "go-librespot $VERSION installed and running."
