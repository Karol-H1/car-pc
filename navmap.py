"""NavMap: a Kivy widget that draws the offline road map, the route, and the car.

Roads come from map.sqlite (built by tools/build_map_data.py). Positions are Web Mercator meters
("world" coordinates, see geo.to_world). The view is described by a world point that sits at the
anchor on screen, a zoom level (meters per pixel) and a rotation.
"""
import math
import sqlite3
from array import array

from kivy.clock import Clock
from kivy.graphics import (Color, InstructionGroup, Line, PopMatrix, PushMatrix, Rectangle,
                           Rotate, Scale, Translate, Triangle)
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.stencilview import StencilView

import config
import geo

BACKGROUND = (0.11, 0.12, 0.14, 1)
ROUTE_COLOR = (0.18, 0.5, 0.95, 1)
ROUTE_EDGE = (0.07, 0.22, 0.45, 1)
CAR_COLOR = (0.18, 0.5, 0.95, 1)

# Color and width (pixels) for each road class number from tools/build_map_data.py.
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
MIN_SEGMENT = 2  # pixels; shorter line pieces get merged
LONG_PRESS_SECONDS = 0.6
TAP_SLOP = 12    # pixels a finger can wander before a press counts as a drag


def smallest_class_shown(mpp):
    """Hide small streets when zoomed out: returns the highest road class number to draw."""
    for limit, road_class in ((3, 6), (10, 5), (25, 4), (60, 3), (150, 2)):
        if mpp < limit:
            return road_class
    return 1


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
        self.db = sqlite3.connect(config.MAP_DB) if config.MAP_DB.exists() else None
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
        """Fetch the roads around the view from map.sqlite and redraw them."""
        r = self.view_radius() * 1.5  # extra margin so small pans don't need a reload
        cx, cy = self.view_center
        self.origin = self.view_center
        self.drawn_mpp = self.mpp
        self.drawn_box = (cx - r, cy - r, cx + r, cy + r)

        self.roads.clear()
        if self.db is not None:
            rows = self.db.execute(
                "SELECT r.cls, r.coords FROM roads_index i JOIN roads r ON r.id = i.id "
                "WHERE i.maxx >= ? AND i.minx <= ? AND i.maxy >= ? AND i.miny <= ? AND i.mincls <= ? "
                "ORDER BY r.cls DESC",  # small roads first, so big roads are drawn on top
                (cx - r, cx + r, cy - r, cy + r, smallest_class_shown(self.mpp))).fetchall()
            width_scale = 1.0 if self.mpp < 8 else 0.75 if self.mpp < 40 else 0.5
            current_class = None
            for road_class, blob in rows:
                points = self.to_drawn(array("d", blob))
                if len(points) < 4:
                    continue  # the whole road fits in one pixel at this zoom
                if road_class != current_class:
                    color, width = ROAD_STYLES[road_class]
                    self.roads.add(Color(*color))
                    current_class = road_class
                self.roads.add(Line(points=points, width=max(1.01, width * width_scale),
                                    cap="round", joint="round"))
        self.draw_route()
        self.update_view()

    def to_drawn(self, coords):
        """Flat [x, y, x, y, ...] world coordinates to the small numbers used for drawing.

        Points closer than a pixel or so to the previous one are dropped: they add nothing visible,
        and Kivy draws thick lines with gaps when their points are bunched that tightly."""
        ox, oy, mpp = self.origin[0], self.origin[1], self.drawn_mpp
        out = []
        last_x = last_y = None
        last_i = len(coords) - 2
        for i in range(0, len(coords), 2):
            x, y = (coords[i] - ox) / mpp, (coords[i + 1] - oy) / mpp
            if last_x is None or abs(x - last_x) + abs(y - last_y) >= MIN_SEGMENT or i == last_i:
                out += (x, y)
                last_x, last_y = x, y
        return out

    def draw_route(self):
        self.route_lines.clear()
        if len(self.route_world) < 2:
            return
        points = self.to_drawn([v for point in self.route_world for v in point])
        self.route_lines.add(Color(*ROUTE_EDGE))
        self.route_lines.add(Line(points=points, width=7, cap="round", joint="round"))
        self.route_lines.add(Color(*ROUTE_COLOR))
        self.route_lines.add(Line(points=points, width=5, cap="round", joint="round"))

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
