#!/usr/bin/env bash
# Runs the head unit, and starts it again if it ever crashes. Quitting on purpose (Esc) stops it.
# Started at login by ~/.config/autostart/carpc.desktop (see install_autostart.sh).
cd "$(dirname "$0")/.."

# Already set inside the desktop session; needed when started over SSH.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DISPLAY="${DISPLAY:-:0}"

while true; do
    ~/.venvs/carpc/bin/python main.py >> /tmp/carpc.log 2>&1
    status=$?
    if [ "$status" -eq 0 ]; then
        break
    fi
    echo "$(date): head unit exited with status $status, restarting" >> /tmp/carpc.log
    sleep 3
done
