#!/usr/bin/env bash
# Sets up the ignition and reverse signals: the GPIO library, and permission for the head unit to
# power the Pi off when the key turns off (without a password prompt).
# Run on the Pi from the repo:  bash system/install_car_signals.sh   (asks for your password once)
set -e
cd "$(dirname "$0")/.."

~/.venvs/carpc/bin/pip install -q gpiod

# Allow this user (and only this user) to power off and reboot, even with an SSH session open.
sudo tee /etc/polkit-1/rules.d/50-carpc-poweroff.rules > /dev/null <<EOF
// Installed by car-pc/system/install_car_signals.sh: lets the head unit shut the Pi down
// when the car's key turns off.
polkit.addRule(function (action, subject) {
    if (subject.user == "$USER" &&
        (action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
         action.id == "org.freedesktop.login1.reboot" ||
         action.id == "org.freedesktop.login1.reboot-multiple-sessions")) {
        return polkit.Result.YES;
    }
});
EOF

answer=$(busctl call org.freedesktop.login1 /org/freedesktop/login1 \
    org.freedesktop.login1.Manager CanPowerOff)
echo "Power off allowed: $answer (should say \"yes\")"
