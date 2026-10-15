"""Reusable pieces of the interface. Their looks live in headunit.kv; behavior and animation here."""
import math
import random

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.properties import (BooleanProperty, ColorProperty, ListProperty, NumericProperty,
                             StringProperty)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

import config
import theme


class Shown:
    """Mixin: fades a widget in and out with `shown`, and makes it ignore touches while hidden.
    (Kivy's `disabled` would hide the look but still swallow touches meant for what's underneath.)"""
    shown = BooleanProperty(True)
    fade = NumericProperty(0.2)

    def on_shown(self, _, shown):
        Animation.cancel_all(self, "opacity")
        if self.fade:
            Animation(opacity=1 if shown else 0, d=self.fade).start(self)
        else:
            self.opacity = 1 if shown else 0

    def on_touch_down(self, touch):
        return super().on_touch_down(touch) if self.shown else False

    def on_touch_move(self, touch):
        return super().on_touch_move(touch) if self.shown else False

    def on_touch_up(self, touch):
        return super().on_touch_up(touch) if self.shown else False


class HideBox(Shown, BoxLayout):
    pass


class Overlay(Shown, FloatLayout):
    """A full-screen layer (incoming call, reverse camera, startup). While shown it takes every
    touch, so nothing underneath reacts."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.opacity = 1 if self.shown else 0

    def on_touch_down(self, touch):
        if not self.shown:
            return False
        super().on_touch_down(touch)
        return True

    def on_touch_move(self, touch):
        if not self.shown:
            return False
        super().on_touch_move(touch)
        return True

    def on_touch_up(self, touch):
        if not self.shown:
            return False
        super().on_touch_up(touch)
        return True


class Panel(Shown, FloatLayout):
    """A pop-up card over part of the screen (the call card). While shown it takes the touches that
    land on it, so nothing underneath reacts, and lets everything else through."""

    def on_touch_down(self, touch):
        if not self.shown or not self.collide_point(*touch.pos):
            return False
        super().on_touch_down(touch)
        return True


class IconButton(ButtonBehavior, Label):
    icon = StringProperty("")


class RoundButton(ButtonBehavior, Label):
    icon = StringProperty("")
    fill = ColorProperty(theme.ACCENT)
    icon_color = ColorProperty((0.02, 0.03, 0.05, 1))


class RailButton(ButtonBehavior, BoxLayout):
    icon = StringProperty("")
    caption = StringProperty("")
    active = BooleanProperty(False)


class SeekBar(Slider):
    """A Slider that playback doesn't move while a finger is on it, and that reports where the
    finger let go (on_seek) instead of every step along the way."""
    dragging = BooleanProperty(False)

    __events__ = ("on_seek",)

    def on_touch_down(self, touch):
        if not self.disabled and self.collide_point(*touch.pos):
            self.dragging = True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.dragging and touch.grab_current is self:
            self.dragging = False
            super().on_touch_up(touch)
            self.dispatch("on_seek", self.value)
            return True
        return super().on_touch_up(touch)

    def on_seek(self, value):
        pass


class VolumeSlider(Slider):
    """A Slider with the same look as the song progress bar (style in headunit.kv)."""


class AmbientBackground(Widget):
    """Big soft glows drifting slowly behind everything, colored from the current album cover."""
    accent = ColorProperty(theme.ACCENT)

    # Where each glow wanders: (x, y) as fractions of the screen, and its size.
    PATHS = [(0.12, 0.88, 1.0), (0.9, 0.12, 1.1), (0.62, 0.55, 0.75)]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.time = random.uniform(0, 100)
        glow = theme.glow_texture()
        with self.canvas:
            Color(*theme.BACKGROUND)
            self.base = Rectangle()
            self.glows = [(Color(), Rectangle(texture=glow)) for _ in self.PATHS]
        self.bind(pos=self.layout, size=self.layout, accent=self.recolor)
        self.recolor()
        if config.AMBIENT_FPS:
            Clock.schedule_interval(self.drift, 1 / config.AMBIENT_FPS)

    def recolor(self, *args):
        colors = [theme.with_alpha(self.accent, 0.30),
                  theme.with_alpha(theme.shift_hue(self.accent, 50, value=0.85), 0.24),
                  theme.with_alpha(theme.shift_hue(self.accent, -45, value=0.7), 0.14)]
        for (color, _), rgba in zip(self.glows, colors):
            color.rgba = rgba

    def drift(self, dt):
        self.time += dt
        self.layout()

    def layout(self, *args):
        self.base.pos, self.base.size = self.pos, self.size
        w, h, t = self.width, self.height, self.time
        for i, ((_, rect), (fx, fy, scale)) in enumerate(zip(self.glows, self.PATHS)):
            d = max(w, h) * scale * 1.15
            x = w * fx + math.sin(t * 0.06 + i * 2.1) * w * 0.12
            y = h * fy + math.cos(t * 0.045 + i * 1.3) * h * 0.16
            rect.pos, rect.size = (self.x + x - d / 2, self.y + y - d / 2), (d, d)


class EqualizerBars(Widget):
    """Four little bars that dance while music plays."""
    playing = BooleanProperty(False)
    color = ColorProperty(theme.ACCENT)
    levels = ListProperty([0.3, 0.6, 0.45, 0.8])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.targets = list(self.levels)
        self.event = None

    def on_playing(self, _, playing):
        if playing and self.event is None:
            self.event = Clock.schedule_interval(self.step, 1 / 12)
        elif not playing and self.event is not None:
            self.event.cancel()
            self.event = None
            Animation(levels=[0.2, 0.2, 0.2, 0.2], d=0.4).start(self)

    def step(self, dt):
        self.targets = [random.uniform(0.15, 1) if random.random() < 0.35 else t for t in self.targets]
        self.levels = [level + (target - level) * 0.45 for level, target in zip(self.levels, self.targets)]


class PulseRings(Widget):
    """Rings that ripple outward, like a ringing phone."""
    running = BooleanProperty(False)
    color = ColorProperty(theme.GOOD)
    inner = NumericProperty(60)  # radius the rings start from

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas:
            self.rings = [(Color(), Line(width=2)) for _ in range(3)]
        self.phase = 0
        self.event = None

    def on_running(self, _, running):
        if running and self.event is None:
            self.event = Clock.schedule_interval(self.step, 1 / 30)
        elif not running and self.event is not None:
            self.event.cancel()
            self.event = None
            for color, _ in self.rings:
                color.a = 0

    def step(self, dt):
        self.phase = (self.phase + dt / 2.4) % 1
        reach = min(self.size) / 2 - self.inner
        for i, (color, line) in enumerate(self.rings):
            p = (self.phase + i / len(self.rings)) % 1
            color.rgba = theme.with_alpha(self.color, 0.55 * (1 - p))
            line.circle = (self.center_x, self.center_y, self.inner + reach * p)
            line.width = 1 + 3 * (1 - p)


class ParkingGuides(Widget):
    """The colored distance lines drawn over the reverse camera (red = close, green = far)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *args):
        self.canvas.clear()
        w, h, x0, y0 = self.width, self.height, self.x, self.y
        # Guide edges: wide at the bottom of the screen (near the bumper), narrowing into the distance.
        def edge(t, side):
            near, far = 0.20 * w, 0.36 * w
            return x0 + w / 2 + side * (w / 2 - (near + (far - near) * t)), y0 + h * (0.04 + 0.5 * t)
        bands = [(0.0, 0.33, theme.DANGER), (0.33, 0.66, theme.WARNING), (0.66, 1.0, theme.GOOD)]
        with self.canvas:
            for start, end, color in bands:
                Color(*theme.with_alpha(color, 0.9))
                for side in (-1, 1):
                    Line(points=[*edge(start, side), *edge(end, side)], width=3, cap="round")
                tick = (w * 0.05) * (1 - 0.5 * start)
                for side in (-1, 1):
                    x, y = edge(start, side)
                    Line(points=[x, y, x - side * tick, y], width=3, cap="round")
