"""The USB GPS (a u-blox 7 "VK-162" style dongle), read straight from its serial port.

The dongle sends NMEA text sentences once a second. Only $GPRMC is needed: it has the fix status,
position, speed and direction of travel. No gpsd needed. Nothing in here touches Kivy; the callback
runs on a background thread, so callers hand results to the main thread themselves.
"""
import glob
import os
import threading
import time

try:
    import termios
    import tty
except ImportError:  # Windows: there's no GPS serial port to read anyway
    termios = tty = None
from dataclasses import dataclass

METERS_PER_SECOND_PER_KNOT = 0.514444
# Below this speed the GPS's direction of travel is mostly noise, so keep the last good one.
HEADING_MIN_SPEED = 1.5
# With no fix sentence for this long, report that the fix is lost.
STALE_SECONDS = 4


def ubx(message_class, message_id, payload):
    """A u-blox binary (UBX) command with its checksum."""
    body = bytes([message_class, message_id]) + len(payload).to_bytes(2, "little") + payload
    a = b = 0
    for byte in body:
        a = (a + byte) & 0xFF
        b = (b + a) & 0xFF
    return bytes([0xB5, 0x62]) + body + bytes([a, b])


# UBX-CFG-NAV5 with only the "dynamic model" field applied: 4 = automotive (smoother for driving).
# The dongle forgets it when unplugged, so it's sent every time the GPS is opened.
AUTOMOTIVE_MODE = ubx(0x06, 0x24, bytes([0x01, 0x00, 0x04]) + bytes(33))


@dataclass
class Fix:
    lat: float
    lon: float
    heading: float
    speed: float  # meters per second


def find_device():
    for pattern in ("/dev/serial/by-id/*u-blox*", "/dev/serial/by-id/*GPS*", "/dev/serial/by-id/*GNSS*"):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def checksum_ok(sentence):
    body, _, given = sentence.partition("*")
    value = 0
    for char in body[1:]:
        value ^= ord(char)
    return given[:2].upper() == f"{value:02X}"


def degrees(value, hemisphere):
    """NMEA 'ddmm.mmmm' (or 'dddmm.mmmm') to signed decimal degrees."""
    point = value.index(".")
    result = int(value[:point - 2]) + float(value[point - 2:]) / 60
    return -result if hemisphere in ("S", "W") else result


class Gps:
    def __init__(self, on_update):
        """Calls on_update(present, fix) on a background thread: present says whether the dongle is
        plugged in, fix is a Fix or None while it's still searching for satellites."""
        self.on_update = on_update
        self.heading = 0.0
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            device = find_device() if termios else None
            if device is None:
                self.on_update(False, None)
                time.sleep(3)
                continue
            try:
                self.read(device)
            except (OSError, ValueError, *([termios.error] if termios else [])):
                pass  # unplugged; look for it again
            self.on_update(False, None)
            time.sleep(2)

    def read(self, device):
        fd = os.open(device, os.O_RDWR | os.O_NOCTTY)
        try:
            tty.setraw(fd)  # no echo back to the dongle, no line mangling
            os.write(fd, AUTOMOTIVE_MODE)
            buffer = b""
            last_report = 0.0
            self.on_update(True, None)
            while True:
                chunk = os.read(fd, 1024)
                if not chunk:
                    return
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                for line in lines:
                    fix = self.parse(line.decode("ascii", "ignore").strip())
                    if fix is not False:
                        self.on_update(True, fix)
                        last_report = time.monotonic()
                if time.monotonic() - last_report > STALE_SECONDS:
                    self.on_update(True, None)
                    last_report = time.monotonic()
        finally:
            os.close(fd)

    def parse(self, sentence):
        """A Fix (or None for 'no fix') from an RMC sentence; False for anything else."""
        if not sentence.startswith("$") or sentence[3:6] != "RMC" or not checksum_ok(sentence):
            return False
        fields = sentence.split("*")[0].split(",")
        if len(fields) < 9 or fields[2] != "A" or not fields[3] or not fields[5]:
            return None
        speed = float(fields[7] or 0) * METERS_PER_SECOND_PER_KNOT
        if fields[8] and speed >= HEADING_MIN_SPEED:
            self.heading = float(fields[8])
        return Fix(degrees(fields[3], fields[4]), degrees(fields[5], fields[6]), self.heading, speed)
