"""NavMap: a Kivy widget that draws the offline road map, the route, and the car.

Roads come from map.sqlite (built by tools/build_map_data.py). Positions are Web Mercator meters
("world" coordinates, see geo.to_world). The view is described by a world point that sits at the
anchor on screen, a zoom level (meters per pixel) and a rotation.
"""
import math
import sqlite3
import threading

import numpy as np
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import (Color, InstructionGroup, Mesh, PopMatrix, PushMatrix, Rectangle, Rotate,
                           Scale, Translate, Triangle)
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.stencilview import StencilView

import config
import geo

BACKGROUND = (0.11, 0.12, 0.14, 1)
ROUTE_COLOR = (0.18, 0.5, 0.95, 1)
ROUTE_EDGE = (0.07, 0.22, 0.45, 1)
CAR_COLOR = (0.18, 0.5, 0.95, 1)

# Color and half-width (pixels) for each road class number from tools/build_map_data.py.
ROAD_STYLES = [
    ((0.86, 0.62, 0.30, 1), 6.0),  # 0 motorway
    ((0.78, 0.68, 0.42, 1), 5.0),  # 1 trunk
    ((0.56, 0.58, 0.63, 1), 4.5),  # 2 primary
    ((0.47, 0.49, 0.54, 1), 4.0),  # 3 secondary
    ((0.40, 0.42, 0.47, 1), 3.5),  # 4 tertiary
    ((0.31, 0.33, 0.37, 1), 2.5),  # 5 residential
    ((0.24, 0.26, 0.30, 1), 1.5),  # 6 service
]

MIN_MPP = 0.5    # closest zoom, meters per pixel
MAX_MPP = 400    # farthest zoom
DRIVING_MPP = 3  # zoom used while following the car
# Each line segment becomes 4 corners, and a Mesh can only number 65535 corners.
SEGMENTS_PER_MESH = 16000
QUAD_INDICES = (np.array([0, 1, 2, 2, 1, 3], np.uint16)
                + 4 * np.arange(SEGMENTS_PER_MESH, dtype=np.uint16)[:, None]).ravel()
# Street names
LABEL_FONT_SIZE = 13
LABEL_COLOR = (0.86, 0.88, 0.92, 1)
LABEL_MAX_MPP = 8        # only label streets when zoomed in this close
LABEL_MAX_CLASS = 5      # don't label service roads (driveways, parking lots)
MAX_LABELS = 60
LABEL_MAX_BEND = 30      # degrees a road may curve under one name
SAME_NAME_SPACING = 300  # pixels between repeats of one street's name
# Place names (rank numbers from tools/build_map_data.py): font size, bold, and the farthest zoom
# (meters per pixel) each rank still shows at.
PLACE_STYLES = [
    (18, True, MAX_MPP),  # 0 city
    (16, True, MAX_MPP),  # 1 town
    (14, False, 100),     # 2 village
    (14, False, 30),      # 3 suburb (large neighborhood)
    (13, False, 20),      # 4 neighborhood
]
PLACE_COLOR = (0.95, 0.96, 0.98, 1)
MAX_PLACE_LABELS = 80
LONG_PRESS_SECONDS = 0.6
TAP_SLOP = 12    # pixels a finger can wander before a press counts as a drag


def smallest_class_shown(mpp):
    """Hide small streets when zoomed out: returns the highest road class number to draw."""
    for limit, road_class in ((3, 6), (10, 5), (25, 4), (60, 3), (150, 2)):
        if mpp < limit:
            return road_class
    return 1


def stroke_meshes(coords, starts, half_width):
    """Turn many polylines into triangles, ready for a few Kivy Meshes.

    coords is an (N, 2) array of every line's points back to back; starts holds the index where
    each line begins. Drawing thousands of roads as one Mesh per color, instead of one Line each,
    is what keeps the Pi's graphics chip fast. Returns a list of (vertices, indices) chunks.
    """
    keep = np.ones(len(coords) - 1, bool)
    keep[np.asarray(starts, np.int64)[1:] - 1] = False  # no segment joining one road's end to the next road
    a, b = coords[:-1][keep], coords[1:][keep]
    direction = b - a
    length = np.hypot(direction[:, 0], direction[:, 1])
    nonzero = length > 1e-6
    a, b, direction = a[nonzero], b[nonzero], direction[nonzero] / length[nonzero, None]
    # Stretching each segment by half its width at both ends fills the gaps at bends.
    along = direction * half_width
    across = np.stack([-direction[:, 1], direction[:, 0]], axis=1) * half_width
    a, b = a - along, b + along
    vertices = np.zeros((len(a), 4, 4), np.float32)  # x, y and two unused texture coordinates
    vertices[:, :, :2] = np.stack([a + across, a - across, b + across, b - across], axis=1)
    return [(vertices[i:i + SEGMENTS_PER_MESH].ravel(),
             QUAD_INDICES[:6 * len(vertices[i:i + SEGMENTS_PER_MESH])])
            for i in range(0, len(vertices), SEGMENTS_PER_MESH)]


def text_width_guess(name):
    return len(name) * LABEL_FONT_SIZE * 0.55 + 6


def straightest_stretch(points):
    """Find the longest run of a road that stays within LABEL_MAX_BEND degrees of straight.

    Returns (length, middle point, angle) for that run, with the middle measured along the road."""
    steps = np.diff(points, axis=0)
    lengths = np.hypot(steps[:, 0], steps[:, 1])
    angles = np.degrees(np.arctan2(steps[:, 1], steps[:, 0]))
    best_length, best_first, best_last = 0.0, 0, 0
    for first in range(len(steps)):
        total = 0.0
        for last in range(first, len(steps)):
            if abs((angles[last] - angles[first] + 180) % 360 - 180) > LABEL_MAX_BEND:
                break
            total += lengths[last]
            if total > best_length:
                best_length, best_first, best_last = total, first, last

    # Walk halfway along the run to find its middle.
    remaining = best_length / 2
    for i in range(best_first, best_last + 1):
        if remaining <= lengths[i] or i == best_last:
            t = 0.0 if lengths[i] == 0 else min(1.0, remaining / lengths[i])
            middle = points[i] + t * steps[i]
            break
        remaining -= lengths[i]
    start, end = points[best_first], points[best_last + 1]
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    return best_length, middle, angle


def join_pieces(pieces):
    """OpenStreetMap splits a street into many pieces (often one per block). Join the pieces that
    share end points back into longer lines, so a name has room to fit."""
    pieces = list(pieces)
    joined = []
    while pieces:
        line = pieces.pop()
        grew = True
        while grew:
            grew = False
            for k, other in enumerate(pieces):
                if np.array_equal(line[-1], other[0]):
                    line = np.vstack([line, other[1:]])
                elif np.array_equal(line[-1], other[-1]):
                    line = np.vstack([line, other[-2::-1]])
                elif np.array_equal(line[0], other[-1]):
                    line = np.vstack([other[:-1], line])
                elif np.array_equal(line[0], other[0]):
                    line = np.vstack([other[:0:-1], line])
                else:
                    continue
                pieces.pop(k)
                grew = True
                break
        joined.append(line)
    return joined


def pick_labels(named_roads):
    """Choose where to write street names. named_roads is a list of (class, name, points) with
    points in drawing units (pixels, 0,0 = middle of the view). Returns [(name, x, y, angle)],
    nearest-first and spread out so labels don't pile up."""
    streets = {}
    for road_class, name, points in named_roads:
        streets.setdefault((road_class, name), []).append(points)

    candidates = []
    for (road_class, name), pieces in streets.items():
        width = text_width_guess(name)
        for points in join_pieces(pieces):
            length, (x, y), angle = straightest_stretch(points)
            if length >= width * 0.9:
                candidates.append((math.hypot(x, y), road_class, name, float(x), float(y), angle, width))

    chosen = []
    for _, _, name, x, y, angle, width in sorted(candidates):  # nearest first
        if len(chosen) == MAX_LABELS:
            break
        crowded = any(math.hypot(x - cx, y - cy) < (width + other_width) * 0.45 or
                      (name == other_name and math.hypot(x - cx, y - cy) < SAME_NAME_SPACING)
                      for other_name, cx, cy, _, other_width in chosen)
        if not crowded:
            chosen.append((name, x, y, angle, width))
    return [(name, x, y, angle) for name, x, y, angle, _ in chosen]


def pick_place_labels(places):
    """places: list of (name, rank, population, x, y) in drawing units. Most important first, and
    none overlapping. Returns [(name, x, y, rank)]."""
    chosen = []
    for name, rank, population, x, y in sorted(places, key=lambda p: (p[1], -p[2])):
        if len(chosen) == MAX_PLACE_LABELS:
            break
        size = PLACE_STYLES[rank][0]
        half_width, half_height = len(name) * size * 0.3 + 8, size * 0.8 + 6
        # Boxes are compared as if the map weren't turned; close enough for spacing names out.
        if all(abs(x - cx) > half_width + cw or abs(y - cy) > half_height + ch
               for _, cx, cy, _, cw, ch in chosen):
            chosen.append((name, x, y, rank, half_width, half_height))
    return [(name, x, y, rank) for name, x, y, rank, _, _ in chosen]


def rotate(x, y, degrees):
    """Rotate a vector counterclockwise."""
    a = math.radians(degrees)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


class NavMap(StencilView):
    following = BooleanProperty(True)  # keep the car in view, pointing up
    mpp = NumericProperty(DRIVING_MPP)  # zoom, in meters per pixel (smaller = closer)

    __events__ = ("on_destination",)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Only the loader thread uses this connection, one load at a time.
        self.db = (sqlite3.connect(config.MAP_DB, check_same_thread=False)
                   if config.MAP_DB.exists() else None)
        self.has_places = self.db is not None and self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'places'").fetchone() is not None
        self.loading = False
        self.view_center = geo.to_world(*config.DEFAULT_POSITION)
        self.rotation = 0.0
        self.car = None          # (world x, world y)
        self.car_heading = None  # degrees, smoothed
        self.route_world = []

        # Geometry is stored relative to origin and pre-divided by drawn_mpp, so the numbers sent
        # to the graphics card stay small (precise) and line widths can be given in pixels.
        self.origin = self.view_center
        self.drawn_mpp = self.mpp
        self.drawn_box = None

        # (angle along the road, or None for a place name that stays level; its Rotate; its Scale)
        self.label_parts = []
        self.label_textures = {}   # (name, style) -> rendered text, reused across reloads

        self.touches = {}
        self.press_start = None
        self.long_press = None

        with self.canvas.before:
            Color(*BACKGROUND)
            self.background = Rectangle()
        with self.canvas:
            PushMatrix()
            self.move_to_anchor = Translate()
            self.turn = Rotate(angle=0, origin=(0, 0))
            self.zoom = Scale(1, 1, 1)
            self.move_to_view = Translate()
            self.roads = InstructionGroup()
            self.route_lines = InstructionGroup()
            self.labels = InstructionGroup()
            PopMatrix()
            self.car_marker = InstructionGroup()

        self.reload_soon = Clock.create_trigger(self.reload)
        self.bind(pos=self.update_view, size=self.update_view, mpp=self.update_view)

    def on_destination(self, lat, lon):
        pass

    # ---------- Public controls ----------

    def set_car(self, lat, lon, heading):
        self.car = geo.to_world(lat, lon)
        if self.car_heading is None:
            self.car_heading = heading
        else:
            # Ease toward the new heading so the map doesn't snap at every bend in the road.
            turn = (heading - self.car_heading + 180) % 360 - 180
            self.car_heading = (self.car_heading + turn * 0.25) % 360
        if self.following:
            self.view_center = self.car
            self.rotation = self.car_heading
        self.update_view()

    def set_route(self, points_world):
        self.route_world = points_world
        self.draw_route()

    def recenter(self):
        self.following = True
        self.mpp = DRIVING_MPP
        if self.car:
            self.view_center = self.car
            self.rotation = self.car_heading or 0.0
        self.update_view()

    def show_overview(self, points_world):
        """Zoom out, north up, so the whole list of points fits on screen."""
        if not points_world or not self.width:
            return
        self.following = False
        xs = [x for x, _ in points_world]
        ys = [y for _, y in points_world]
        self.view_center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        self.rotation = 0.0
        fit = max((max(xs) - min(xs)) / self.width, (max(ys) - min(ys)) / self.height) * 1.15
        self.mpp = max(MIN_MPP, min(MAX_MPP, fit))
        self.update_view()

    # ---------- Coordinates ----------

    def anchor(self):
        """Screen point where view_center is drawn: low on the screen while following, so more
        of the road ahead is visible."""
        return self.x + self.width / 2, self.y + self.height * (0.3 if self.following else 0.5)

    def to_screen(self, wx, wy):
        ax, ay = self.anchor()
        dx, dy = rotate((wx - self.view_center[0]) / self.mpp, (wy - self.view_center[1]) / self.mpp,
                        self.rotation)
        return ax + dx, ay + dy

    def to_world(self, sx, sy):
        ax, ay = self.anchor()
        dx, dy = rotate(sx - ax, sy - ay, -self.rotation)
        return self.view_center[0] + dx * self.mpp, self.view_center[1] + dy * self.mpp

    # ---------- Drawing ----------

    def update_view(self, *args):
        """Cheap: moves the already-drawn geometry. Reloads roads only when needed."""
        self.background.pos, self.background.size = self.pos, self.size
        self.move_to_anchor.xy = self.anchor()
        self.turn.angle = self.rotation
        k = self.drawn_mpp / self.mpp
        self.zoom.xyz = (k, k, 1)
        for angle, turn, size in self.label_parts:
            # Keep names readable: street names flip if they'd be upside down, place names stay
            # level however the map turns, and none of them stretch while zooming.
            if angle is None:
                turn.angle = -self.rotation
            else:
                upright = math.cos(math.radians(angle + self.rotation)) >= 0
                turn.angle = angle if upright else angle + 180
            size.xyz = (1 / k, 1 / k, 1)
        self.move_to_view.xy = ((self.origin[0] - self.view_center[0]) / self.drawn_mpp,
                                (self.origin[1] - self.view_center[1]) / self.drawn_mpp)
        self.draw_car()
        if self.needs_reload():
            self.reload_soon()

    def view_radius(self):
        """World distance from the anchor to the farthest corner, whatever the rotation."""
        return math.hypot(self.width, self.height) * self.mpp

    def needs_reload(self):
        if self.drawn_box is None:
            return True
        if not 0.6 < self.mpp / self.drawn_mpp < 1.6:
            return True
        r = self.view_radius()
        cx, cy = self.view_center
        minx, miny, maxx, maxy = self.drawn_box
        return cx - r < minx or cx + r > maxx or cy - r < miny or cy + r > maxy

    def reload(self, *args):
        """Start fetching the roads around the view. The slow part runs on a background thread;
        show_roads() puts the result on screen."""
        if self.loading:
            return  # show_roads() checks again when the current load finishes
        self.loading = True
        r = self.view_radius() * 1.5  # extra margin so small pans don't need a reload
        request = (self.view_center, self.mpp, r)
        threading.Thread(target=self.load_roads, args=(request,), daemon=True).start()

    def load_roads(self, request):
        """Background thread: query map.sqlite and turn the roads into triangles."""
        (cx, cy), mpp, r = request
        layers, labels = [], []
        if self.db is not None:
            rows = self.db.execute(
                "SELECT r.cls, r.coords, r.name FROM roads_index i JOIN roads r ON r.id = i.id "
                "WHERE i.maxx >= ? AND i.minx <= ? AND i.maxy >= ? AND i.miny <= ? AND i.mincls <= ?",
                (cx - r, cx + r, cy - r, cy + r, smallest_class_shown(mpp))).fetchall()
            by_class = {}
            named_roads = []
            for road_class, blob, name in rows:
                by_class.setdefault(road_class, []).append(blob)
                if name and mpp < LABEL_MAX_MPP and road_class <= LABEL_MAX_CLASS:
                    points = (np.frombuffer(blob, np.float64).reshape(-1, 2) - (cx, cy)) / mpp
                    named_roads.append((road_class, name, points))
            labels = [(name, x, y, angle, "street") for name, x, y, angle in pick_labels(named_roads)]
            if self.has_places and mpp >= LABEL_MAX_MPP:
                ranks = [rank for rank, (_, _, max_mpp) in enumerate(PLACE_STYLES) if mpp < max_mpp]
                places = self.db.execute(
                    f"SELECT name, rank, population, x, y FROM places WHERE x BETWEEN ? AND ? "
                    f"AND y BETWEEN ? AND ? AND rank IN ({','.join('?' * len(ranks))})",
                    (cx - r, cx + r, cy - r, cy + r, *ranks)).fetchall()
                places = [(name, rank, population, (x - cx) / mpp, (y - cy) / mpp)
                          for name, rank, population, x, y in places]
                labels += [(name, x, y, None, rank) for name, x, y, rank in pick_place_labels(places)]
            width_scale = 1.0 if mpp < 8 else 0.75 if mpp < 40 else 0.5
            for road_class in sorted(by_class, reverse=True):  # small roads first, big roads on top
                blobs = by_class[road_class]
                coords = (np.frombuffer(b"".join(blobs), np.float64).reshape(-1, 2) - (cx, cy)) / mpp
                lengths = np.fromiter((len(blob) // 16 for blob in blobs), np.int64, len(blobs))
                starts = np.concatenate(([0], np.cumsum(lengths)[:-1]))
                color, width = ROAD_STYLES[road_class]
                layers.append((color, stroke_meshes(coords, starts, width * width_scale)))
        Clock.schedule_once(lambda dt: self.show_roads(request, layers, labels))

    def show_roads(self, request, layers, labels):
        """Main thread: swap the freshly loaded roads in."""
        (cx, cy), mpp, r = request
        self.origin, self.drawn_mpp = (cx, cy), mpp
        self.drawn_box = (cx - r, cy - r, cx + r, cy + r)
        self.roads.clear()
        for color, chunks in layers:
            self.roads.add(Color(*color))
            for vertices, indices in chunks:
                self.roads.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))
        self.draw_labels(labels)
        self.loading = False
        self.draw_route()
        self.update_view()

    def draw_route(self):
        self.route_lines.clear()
        if len(self.route_world) < 2:
            return
        coords = (np.array(self.route_world) - self.origin) / self.drawn_mpp
        for color, half_width in ((ROUTE_EDGE, 6.5), (ROUTE_COLOR, 4.5)):
            self.route_lines.add(Color(*color))
            for vertices, indices in stroke_meshes(coords, [0], half_width):
                self.route_lines.add(Mesh(vertices=vertices, indices=indices, mode="triangles"))

    def draw_labels(self, labels):
        self.labels.clear()
        self.label_parts = []
        if len(self.label_textures) > 500:
            self.label_textures.clear()
        for name, x, y, angle, style in labels:
            texture = self.label_textures.get((name, style))
            if texture is None:
                if style == "street":
                    font_size, bold, color = LABEL_FONT_SIZE, False, LABEL_COLOR
                else:
                    (font_size, bold, _), color = PLACE_STYLES[style], PLACE_COLOR
                text = CoreLabel(text=name, font_size=font_size, bold=bold, color=color,
                                 outline_width=2, outline_color=BACKGROUND[:3])
                text.refresh()
                texture = self.label_textures[(name, style)] = text.texture
            turn, size = Rotate(angle=angle or 0, origin=(0, 0)), Scale(1, 1, 1)
            w, h = texture.size
            for instruction in (PushMatrix(), Translate(x, y), turn, size, Color(1, 1, 1, 1),
                                Rectangle(texture=texture, pos=(-w / 2, -h / 2), size=(w, h)),
                                PopMatrix()):
                self.labels.add(instruction)
            self.label_parts.append((angle, turn, size))

    def draw_car(self):
        self.car_marker.clear()
        if self.car is None:
            return
        x, y = self.to_screen(*self.car)
        # Screen direction of the arrow: the car's heading minus however far the map is turned.
        angle = -(self.car_heading - self.rotation)
        def corner(distance, offset):
            dx, dy = rotate(0, distance, angle + offset)
            return x + dx, y + dy
        for color, size in (((1, 1, 1, 1), 1.35), (CAR_COLOR, 1.0)):
            self.car_marker.add(Color(*color))
            self.car_marker.add(Triangle(points=[*corner(16 * size, 0), *corner(12 * size, 140),
                                                 *corner(12 * size, -140)]))

    # ---------- Touch: drag to pan, pinch or scroll to zoom, hold to pick a destination ----------

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if touch.is_mouse_scrolling:
            # Kivy calls rolling the wheel away from you "scrolldown".
            self.zoom_by(1 / 1.25 if touch.button == "scrolldown" else 1.25)
            return True
        touch.grab(self)
        self.touches[touch.uid] = touch.pos
        self.cancel_long_press()
        if len(self.touches) == 1:
            self.press_start = touch.pos
            self.long_press = Clock.schedule_once(lambda dt: self.pick_destination(touch.pos),
                                                  LONG_PRESS_SECONDS)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        previous = dict(self.touches)
        self.touches[touch.uid] = touch.pos
        if self.press_start and math.dist(self.press_start, touch.pos) > TAP_SLOP:
            self.cancel_long_press()
        if len(self.touches) == 1:
            if self.long_press is None:  # only pan once it's clearly a drag
                px, py = previous[touch.uid]
                dx, dy = rotate(touch.x - px, touch.y - py, -self.rotation)
                self.following = False
                self.view_center = (self.view_center[0] - dx * self.mpp, self.view_center[1] - dy * self.mpp)
                self.update_view()
        elif len(self.touches) == 2:
            before = math.dist(*previous.values())
            after = math.dist(*self.touches.values())
            if before > 0 and after > 0:
                self.zoom_by(before / after)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        self.touches.pop(touch.uid, None)
        self.cancel_long_press()
        return True

    def cancel_long_press(self):
        if self.long_press is not None:
            self.long_press.cancel()
            self.long_press = None
        self.press_start = None

    def pick_destination(self, screen_pos):
        self.long_press = None
        self.press_start = None
        self.dispatch("on_destination", *geo.to_latlon(*self.to_world(*screen_pos)))

    def zoom_by(self, factor):
        self.mpp = max(MIN_MPP, min(MAX_MPP, self.mpp * factor))
