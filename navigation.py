"""Offline routing with Valhalla, and tracking the car's progress along a route.

Nothing in here touches Kivy, so it can be tested on its own.
"""
import bisect
import json
import math
import threading
from dataclasses import dataclass

from valhalla import Actor, get_config

import config
import geo

ARRIVED_METERS = 25
OFF_ROUTE_METERS = 60


def routing_config():
    cfg = get_config(tile_extract="", tile_dir=config.ROUTING_TILES)
    cfg["mjolnir"]["traffic_extract"] = ""
    return cfg


@dataclass
class Progress:
    instruction: str      # the next thing to do, e.g. "Turn right onto Main Street."
    maneuver_type: int    # Valhalla's number for the kind of turn (theme.MANEUVER_ICONS)
    street: str           # the street that maneuver leads onto, if it has a name
    to_maneuver: float    # meters until that maneuver
    remaining: float      # meters left in the whole trip
    time_left: float      # seconds left in the whole trip
    off_route: float      # meters between the car and the route line
    arrived: bool


class Route:
    def __init__(self, trip):
        leg = trip["legs"][0]
        self.maneuvers = leg["maneuvers"]
        self.points = geo.decode_polyline(leg["shape"])
        self.world = [geo.to_world(lat, lon) for lat, lon in self.points]
        self.cumulative = [0.0]
        for (lat1, lon1), (lat2, lon2) in zip(self.points, self.points[1:]):
            self.cumulative.append(self.cumulative[-1] + geo.distance_m(lat1, lon1, lat2, lon2))
        # Mercator stretches distances by 1/cos(latitude); this undoes it near the route.
        self.mercator_to_meters = math.cos(math.radians(self.points[0][0]))
        self.last_index = 0

    @property
    def length(self):
        return self.cumulative[-1]

    def locate(self, lat, lon):
        """Where is the car on the route? Returns (meters along the route, meters off the route)."""
        if len(self.world) < 2:
            return 0.0, 0.0
        x, y = geo.to_world(lat, lon)
        # Only search just behind and ahead of the last match, so a route that loops back or
        # crosses itself (overpasses) doesn't make the car jump to the wrong part.
        start = max(0, self.last_index - 5)
        end = min(len(self.world) - 1, self.last_index + 300)
        best_distance, best_index, best_t = math.inf, start, 0.0
        for i in range(start, end):
            (ax, ay), (bx, by) = self.world[i], self.world[i + 1]
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy
            t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length_sq))
            distance = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
            if distance < best_distance:
                best_distance, best_index, best_t = distance, i, t
        self.last_index = best_index
        segment = self.cumulative[best_index + 1] - self.cumulative[best_index]
        return self.cumulative[best_index] + best_t * segment, best_distance * self.mercator_to_meters

    def point_at(self, along):
        """The (lat, lon, heading) found a given number of meters along the route."""
        i = max(0, min(bisect.bisect_right(self.cumulative, along) - 1, len(self.points) - 2))
        segment = self.cumulative[i + 1] - self.cumulative[i]
        t = 0.0 if segment == 0 else max(0.0, min(1.0, (along - self.cumulative[i]) / segment))
        (lat1, lon1), (lat2, lon2) = self.points[i], self.points[i + 1]
        # Repeated points have no direction, so take the heading from the next real segment.
        j = i
        while (lat2, lon2) == (lat1, lon1) and j + 2 < len(self.points):
            j += 1
            lat2, lon2 = self.points[j + 1]
        heading = geo.bearing_deg(lat1, lon1, lat2, lon2)
        return lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t, heading

    def progress(self, lat, lon):
        along, off_route = self.locate(lat, lon)

        # The upcoming maneuver is the first one that starts ahead of the car.
        upcoming = self.maneuvers[-1]
        for maneuver in self.maneuvers[1:]:
            if self.cumulative[maneuver["begin_shape_index"]] > along + 1:
                upcoming = maneuver
                break
        to_maneuver = max(0.0, self.cumulative[upcoming["begin_shape_index"]] - along)

        # Time left: the unfinished part of the current maneuver, plus every maneuver after it.
        time_left = 0.0
        for maneuver in self.maneuvers:
            start = self.cumulative[maneuver["begin_shape_index"]]
            end = self.cumulative[maneuver["end_shape_index"]]
            if end <= along:
                continue
            if start >= along:
                time_left += maneuver["time"]
            else:
                time_left += maneuver["time"] * (end - along) / (end - start)

        remaining = self.length - along
        street = ", ".join(upcoming.get("street_names") or upcoming.get("begin_street_names") or [])
        return Progress(upcoming["instruction"], upcoming.get("type", 0), street, to_maneuver,
                        remaining, time_left, off_route, remaining < ARRIVED_METERS)


class Navigator:
    """Plans routes on a background thread, so the screen never freezes while Valhalla works."""

    def __init__(self):
        self.actor = None
        self.lock = threading.Lock()

    def plan(self, start, destination, on_done):
        """Find a route from start to destination ((lat, lon) pairs).

        on_done(route, error) is called from the background thread when finished; exactly one of
        route and error is None.
        """
        threading.Thread(target=self._plan, args=(start, destination, on_done), daemon=True).start()

    def _plan(self, start, destination, on_done):
        try:
            with self.lock:
                if self.actor is None:
                    self.actor = Actor(routing_config())
                result = self.actor.route({
                    "locations": [{"lat": start[0], "lon": start[1]},
                                  {"lat": destination[0], "lon": destination[1]}],
                    "costing": "auto",
                    "units": "miles",
                })
            if isinstance(result, str):
                result = json.loads(result)
            on_done(Route(result["trip"]), None)
        except FileNotFoundError:
            on_done(None, f"No routing data in {config.ROUTING_TILES}. Run tools/build_routing_tiles.py.")
        except Exception as error:  # Valhalla raises when no road route exists between the points
            on_done(None, str(error))
