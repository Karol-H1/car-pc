"""Paths and settings shared by the app and the data-building tools."""
import os
from pathlib import Path

# Map and routing data is large, so it lives outside the repo (and outside OneDrive).
# Set the CARPC_DATA environment variable to keep it somewhere else.
DATA_DIR = Path(os.environ.get("CARPC_DATA", Path.home() / "carpc-data"))
MAP_DB = DATA_DIR / "map.sqlite"
ROUTING_TILES = DATA_DIR / "valhalla_tiles"

MODEL_FILE = Path("/proc/device-tree/model")
ON_PI = MODEL_FILE.exists() and "Raspberry Pi" in MODEL_FILE.read_text(errors="ignore")

# Where the car is when there's no GPS (laptop testing): Boston, MA.
DEFAULT_POSITION = (42.3601, -71.0589)

# How fast the demo drive moves along the route, in meters per second (40 m/s is about 90 mph).
DEMO_SPEED = 40

# Look and feel. AMBIENT_FPS is how often the glowing background drifts (0 = keep it still).
# CARPC_NO_SPLASH=1 skips the startup animation (handy for tests).
AMBIENT_FPS = 20
SHOW_SPLASH = not os.environ.get("CARPC_NO_SPLASH")

# Dashcam. The camera is found by (part of) its name; recordings are 1-minute MKV files. The oldest
# loop minutes are deleted to stay under DASHCAM_MAX_GB and keep DASHCAM_MIN_FREE_GB free on the disk.
DASHCAM_DIR = Path(os.environ.get("CARPC_DASHCAM", Path.home() / "dashcam"))
DASHCAM_CAMERA = "UGREEN Camera"
DASHCAM_SIZE = "1280x720"
DASHCAM_FPS = 15
DASHCAM_MAX_GB = 20
DASHCAM_MIN_FREE_GB = 3

# Car signals, through the optocoupler board (docs/car-wiring-guide.md). Pins are GPIO (BCM) numbers:
# GPIO17 is header pin 11, GPIO27 is header pin 13. Most PC817 boards pull their output to ground
# when 12V arrives ("active low"); flip SIGNALS_ACTIVE_LOW if the board turns out to do the opposite.
IGNITION_PIN = 17
REVERSE_PIN = 27
SIGNALS_ACTIVE_LOW = True
# After the key turns off, wait this long before shutting down. Turning the key back on cancels it,
# and it also rides out the moment the accessory power drops while the engine cranks.
IGNITION_OFF_SECONDS = 10
# Really power the Pi off when the key turns off. Keep this False until the car wiring is in: until
# then the shutdown screen runs as a test, and the Pi stays on. (It also only reacts after the key
# has been seen on, so a Pi with nothing wired to its pins never shuts itself down.)
IGNITION_SHUTDOWN = False
