"""The car's ignition (key on) and reverse signals, read from the Pi's GPIO pins.

Both come from the car's 12V wires through the optocoupler board (see docs/car-wiring-guide.md), so
the Pi only ever sees a safe 3.3V signal. The pins are read 10 times a second, and a change only
counts once it has held steady for a moment, so a flickering contact doesn't flip the screen back
and forth. Nothing in here touches Kivy; the callback runs on a background thread.

On a computer without GPIO (the laptop) this does nothing; use the keyboard there instead.
"""
import threading
import time

import config

try:
    import gpiod
    from gpiod.line import Bias, Direction, Value
except ImportError:
    gpiod = None

CHIP = "/dev/gpiochip0"   # the Pi 5's 40-pin header
POLL_SECONDS = 0.1
STEADY_SECONDS = {"ignition": 0.5, "reverse": 0.2}


def available():
    return gpiod is not None and config.ON_PI


class CarSignals:
    def __init__(self, on_change):
        """Calls on_change(name, active) when "ignition" or "reverse" turns on or off, and once for
        each at startup with its current state."""
        self.on_change = on_change
        self.pins = {"ignition": config.IGNITION_PIN, "reverse": config.REVERSE_PIN}
        if available():
            threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                      active_low=config.SIGNALS_ACTIVE_LOW)
        try:
            request = gpiod.request_lines(CHIP, consumer="car-pc",
                                          config={tuple(self.pins.values()): settings})
        except OSError as error:
            print("Car signals unavailable:", error)
            return
        with request:
            states, changed_at = {}, {}
            while True:
                now = time.monotonic()
                for name, pin in self.pins.items():
                    active = request.get_value(pin) == Value.ACTIVE
                    if name not in states:
                        states[name] = active
                        self.on_change(name, active)
                    elif active == states[name]:
                        changed_at.pop(name, None)
                    elif now - changed_at.setdefault(name, now) >= STEADY_SECONDS[name]:
                        states[name] = active
                        changed_at.pop(name)
                        self.on_change(name, active)
                time.sleep(POLL_SECONDS)
