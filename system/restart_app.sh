#!/usr/bin/env bash
# (Re)start the head unit on the Pi's screen. Works from an SSH session too.
# Run on the Pi from the repo:  bash system/restart_app.sh
cd "$(dirname "$0")/.."
pkill -f "bin/python main.py" && sleep 1

export XDG_RUNTIME_DIR="/run/user/$(id -u)" WAYLAND_DISPLAY=wayland-0 DISPLAY=:0
nohup ~/.venvs/carpc/bin/python main.py > /tmp/carpc.log 2>&1 < /dev/null &
sleep 6
if pgrep -f "bin/python main.py" > /dev/null; then
    echo "Head unit running (log: /tmp/carpc.log)"
else
    echo "Head unit failed to start:"
    tail -20 /tmp/carpc.log
fi
