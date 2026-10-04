"""Turn an OpenStreetMap extract (.osm.pbf) into map.sqlite, the road data NavMap draws.

Usage:  python tools/build_map_data.py path/to/region.osm.pbf

Extracts by state: https://download.geofabrik.de/north-america/us.html
"""
import sqlite3
import sys
import time
from array import array
from pathlib import Path

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import geo  # noqa: E402

# OpenStreetMap highway types we draw, mapped to a class number (0 = most important).
# navmap.ROAD_STYLES uses the same numbers.
ROAD_CLASSES = {
    "motorway": 0, "motorway_link": 0,
    "trunk": 1, "trunk_link": 1,
    "primary": 2, "primary_link": 2,
    "secondary": 3, "secondary_link": 3,
    "tertiary": 4, "tertiary_link": 4,
    "residential": 5, "unclassified": 5, "living_street": 5,
    "service": 6,
}

BATCH_SIZE = 5000


class RoadCollector(osmium.SimpleHandler):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.rows = []
        self.count = 0

    def way(self, way):
        road_class = ROAD_CLASSES.get(way.tags.get("highway"))
        if road_class is None:
            return
        coords = array("d")
        for node in way.nodes:
            if node.location.valid():
                coords.extend(geo.to_world(node.location.lat, node.location.lon))
        if len(coords) < 4:
            return
        xs, ys = coords[0::2], coords[1::2]
        self.rows.append((road_class, way.tags.get("name"), coords.tobytes(),
                          min(xs), max(xs), min(ys), max(ys)))
        if len(self.rows) >= BATCH_SIZE:
            self.flush()

    def flush(self):
        for road_class, name, blob, minx, maxx, miny, maxy in self.rows:
            cursor = self.db.execute("INSERT INTO roads (cls, name, coords) VALUES (?, ?, ?)",
                                     (road_class, name, blob))
            self.db.execute("INSERT INTO roads_index VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (cursor.lastrowid, minx, maxx, miny, maxy, road_class, road_class))
        self.count += len(self.rows)
        self.rows = []


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pbf = Path(sys.argv[1])
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = config.MAP_DB.with_suffix(".building")
    temp_path.unlink(missing_ok=True)

    db = sqlite3.connect(temp_path)
    db.execute("CREATE TABLE roads (id INTEGER PRIMARY KEY, cls INTEGER, name TEXT, coords BLOB)")
    # The spatial index also covers the road class, so zoomed-out queries skip small streets quickly.
    db.execute("CREATE VIRTUAL TABLE roads_index USING rtree(id, minx, maxx, miny, maxy, mincls, maxcls)")

    started = time.time()
    print(f"Reading {pbf} ...")
    collector = RoadCollector(db)
    collector.apply_file(str(pbf), locations=True)
    collector.flush()
    db.commit()
    db.close()

    temp_path.replace(config.MAP_DB)
    size_mb = config.MAP_DB.stat().st_size / 1e6
    print(f"Saved {collector.count} roads to {config.MAP_DB} ({size_mb:.0f} MB) in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
