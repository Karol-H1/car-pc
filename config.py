"""Paths and settings shared by the app and the data-building tools."""
import os
from pathlib import Path

# Map and routing data is large, so it lives outside the repo (and outside OneDrive).
# Set the CARPC_DATA environment variable to keep it somewhere else.
DATA_DIR = Path(os.environ.get("CARPC_DATA", Path.home() / "carpc-data"))
MAP_DB = DATA_DIR / "map.sqlite"
ROUTING_TILES = DATA_DIR / "valhalla_tiles"

# Where the car is when there's no GPS (laptop testing): Wilmington, DE.
DEFAULT_POSITION = (39.7391, -75.5398)

# How fast the demo drive moves along the route, in meters per second (40 m/s is about 90 mph).
DEMO_SPEED = 40
