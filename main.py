from datetime import datetime, timedelta
from pathlib import Path

from kivy.config import Config

import config

if config.ON_PI:
    # The touchscreen reaches Kivy twice: as real multitouch from the kernel (the probesysfs
    # provider) and as a mouse the desktop emulates from the same finger. Keep only the real one.
    Config.remove_option("input", "mouse")
else:
    # Without this, right-clicking on a laptop leaves red "fake finger" dots for multitouch testing.
    Config.set("input", "mouse", "mouse,multitouch_on_demand")

from kivy.animation import Animation  # noqa: E402
from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.image import Image as CoreImage  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.properties import (BooleanProperty, ColorProperty, NumericProperty,  # noqa: E402
                             ObjectProperty, OptionProperty, StringProperty)
from kivy.uix.screenmanager import Screen, SlideTransition  # noqa: E402

import artwork  # noqa: E402
import geo  # noqa: E402
import navmap  # noqa: E402,F401  (registers NavMap so headunit.kv can use it)
import theme  # noqa: E402
import widgets  # noqa: E402,F401  (registers the custom widgets for headunit.kv)
from demo_drive import DemoDrive  # noqa: E402
from navigation import OFF_ROUTE_METERS, Navigator  # noqa: E402
from spotify import Spotify  # noqa: E402

if config.ON_PI:
    Window.fullscreen = "auto"  # cover the taskbar; the car screen is the whole display
else:
    Window.size = (800, 480)  # the Pi's screen size, for laptop testing
Window.clearcolor = theme.BACKGROUND

MPH_PER_MPS = 2.23694
SCREEN_ORDER = ["home", "music", "dashcam", "traffic"]  # top to bottom on the side rail
WHERE_TO = ("touch_app", "Where to?", "Hold the map to set a destination")


# The looks of these screens live in headunit.kv. Python only needs the class names.
class HomeScreen(Screen):
    pass


class MusicScreen(Screen):
    pass


class DashcamScreen(Screen):
    pass


class TrafficScreen(Screen):
    pass


class HeadUnitApp(App):
    # Kivy properties: when one of these changes, everything in headunit.kv that uses it redraws.

    # Music
    track_title = StringProperty("Spotify")
    track_artist = StringProperty("Connecting...")
    track_album = StringProperty("")
    is_playing = BooleanProperty(False)
    track_position = NumericProperty(0)  # milliseconds
    track_duration = NumericProperty(0)
    seeking = BooleanProperty(False)     # a finger is on a progress bar
    spotify_connected = BooleanProperty(False)
    cover_texture = ObjectProperty(None, allownone=True)
    backdrop_texture = ObjectProperty(None, allownone=True)
    accent = ColorProperty(theme.ACCENT)  # follows the album cover's color

    # Navigation
    has_route = BooleanProperty(False)
    banner_icon = StringProperty(WHERE_TO[0])
    banner_title = StringProperty(WHERE_TO[1])
    banner_text = StringProperty(WHERE_TO[2])
    eta_arrival = StringProperty("")
    eta_minutes = StringProperty("")
    eta_miles = StringProperty("")
    trip_text = StringProperty("")
    speed_text = StringProperty("")
    gps_fix = BooleanProperty(False)

    # Status bar
    clock_time = StringProperty("")
    clock_ampm = StringProperty("")
    clock_date = StringProperty("")
    wifi_on = BooleanProperty(True)

    # Phone and reverse camera
    phone_status = StringProperty("Phone connected")
    call_state = OptionProperty("none", options=["none", "incoming", "active"])
    caller_name = StringProperty("")
    call_timer = StringProperty("0:00")
    reversing = BooleanProperty(False)

    def on_start(self):
        self.screens = self.root.ids.screens
        self.map = self.screens.get_screen("home").ids.navmap

        self.navigator = Navigator()
        self.route = None
        self.destination = None
        self.rerouting = False
        self.demo = None
        self.car_position = config.DEFAULT_POSITION
        self.map.set_car(*self.car_position, 0)

        self.spotify = Spotify(lambda state: Clock.schedule_once(lambda dt: self.show_spotify(state)))
        self.spotify_state = None
        self.cover_url = None
        Clock.schedule_interval(self.tick_progress, 0.5)

        self.was_playing_before_call = False
        self.call_started = None

        self.tick_clock()
        Clock.schedule_interval(self.tick_clock, 1)
        self.play_splash()

        # Keyboard stand-ins while testing on the laptop:
        #   R = reverse-light wire on/off, D = start a demo drive along the current route.
        Window.bind(on_key_down=self.on_key_down)

    # ---- Startup animation ----

    def play_splash(self):
        splash = self.root.ids.splash
        if not config.SHOW_SPLASH:
            splash.shown = False
            return
        ids = splash.ids
        Animation(glow=0.45, d=0.9, t="out_quad").start(splash)
        Animation(opacity=1, d=0.6, t="out_quad").start(ids.title)
        (Animation(d=0.25) + Animation(width=280, d=0.6, t="out_cubic")).start(ids.line)
        (Animation(d=0.6) + Animation(opacity=1, d=0.4)).start(ids.subtitle)
        Clock.schedule_once(lambda dt: setattr(splash, "shown", False), 2.0)

    # ---- Status bar ----

    def tick_clock(self, *args):
        now = datetime.now()
        self.clock_time = now.strftime("%I:%M").lstrip("0")
        self.clock_ampm = now.strftime("%p")
        self.clock_date = f"{now:%a}, {now:%b} {now.day}"
        if config.ON_PI:
            wifi = Path("/sys/class/net/wlan0/operstate")
            self.wifi_on = wifi.exists() and wifi.read_text().strip() == "up"

    # ---- Screens ----

    def switch_to(self, name):
        if name == self.screens.current:
            return
        going_down = SCREEN_ORDER.index(name) > SCREEN_ORDER.index(self.screens.current)
        self.screens.transition = SlideTransition(direction="up" if going_down else "down",
                                                  duration=0.28)
        self.screens.current = name

    def reverse_on(self):
        self.reversing = True

    def reverse_off(self):
        self.reversing = False

    def on_key_down(self, window, key, scancode, codepoint, modifiers):
        if codepoint == "r":
            self.reversing = not self.reversing
        elif codepoint == "d":
            self.start_demo_drive()

    # ---- Navigation ----

    def set_banner(self, icon, title, text):
        self.banner_icon, self.banner_title, self.banner_text = icon, title, text

    def navigate_to(self, lat, lon):
        self.destination = (lat, lon)
        self.set_banner("near_me", "Finding route", "Working it out offline...")
        self.plan_route(show_overview=True)

    def plan_route(self, show_overview=False):
        def done(route, error):
            # Valhalla finishes on a background thread; widgets may only be changed on the main
            # thread, so hand the result over with the Clock.
            Clock.schedule_once(lambda dt: self.on_route_ready(route, error, show_overview))
        self.navigator.plan(self.car_position, self.destination, done)

    def on_route_ready(self, route, error, show_overview):
        self.rerouting = False
        if error:
            print("Routing failed:", error)
            self.set_banner("warning", "No route", "Hold the map to try another spot")
            return
        self.route = route
        self.has_route = True
        place = self.map.nearest_place(*self.destination)
        self.trip_text = f"To {place}" if place else ""
        self.map.set_route(route.world)
        if show_overview:
            self.map.show_overview(route.world)
        self.update_guidance()

    def cancel_route(self):
        self.route = self.destination = None
        self.has_route = False
        self.trip_text = ""
        if self.demo:
            self.demo.stop()
            self.demo = None
            self.speed_text = ""
            self.gps_fix = False
        self.map.set_route([])
        self.set_banner(*WHERE_TO)

    def start_demo_drive(self):
        if self.route is None:
            return
        if self.demo:
            self.demo.stop()
        self.route.last_index = 0
        self.demo = DemoDrive(self.route, self.on_position, config.DEMO_SPEED)
        self.map.recenter()

    def on_position(self, lat, lon, heading, speed=None):
        """Called with every new position: from the demo drive now, from the GPS later.
        speed is in meters per second, or None if unknown."""
        self.car_position = (lat, lon)
        self.gps_fix = True
        self.speed_text = "" if speed is None else f"{speed * MPH_PER_MPS:.0f}"
        self.map.set_car(lat, lon, heading)
        self.update_guidance()

    def update_guidance(self):
        if self.route is None:
            return
        progress = self.route.progress(*self.car_position)
        if progress.arrived:
            self.cancel_route()
            self.set_banner("sports_score", "You've arrived", "Hold the map to go somewhere else")
            return
        if progress.off_route > OFF_ROUTE_METERS and not self.rerouting:
            self.rerouting = True
            self.set_banner("near_me", "Rerouting", "Finding a new way...")
            self.plan_route()
            return
        self.set_banner(theme.MANEUVER_ICONS.get(progress.maneuver_type, "straight"),
                        geo.format_distance(progress.to_maneuver),
                        progress.street or progress.instruction)
        arrival = datetime.now() + timedelta(seconds=progress.time_left)
        self.eta_arrival = arrival.strftime("%I:%M").lstrip("0")
        self.eta_minutes = f"{max(1, round(progress.time_left / 60))}"
        self.eta_miles = f"{progress.remaining / geo.METERS_PER_MILE:.1f}"

    # ---- Music (Spotify) ----

    def show_spotify(self, state):
        self.spotify_connected = state.connected
        if not state.connected:
            self.track_title, self.track_artist = "Spotify", "Not running"
        elif not state.active or not state.title:
            self.track_title, self.track_artist = "Nothing playing", "Pick \"Civic\" in the Spotify app"
        else:
            self.track_title, self.track_artist = state.title, state.artist
        self.track_album = state.album if state.active else ""
        self.is_playing = state.playing
        self.spotify_state = state
        self.track_duration = state.duration if state.active else 0
        self.tick_progress()

        cover_url = state.cover_url if state.active else ""
        if cover_url != self.cover_url:
            self.cover_url = cover_url
            if cover_url:
                artwork.prepare(cover_url, lambda *result: Clock.schedule_once(
                    lambda dt: self.show_artwork(*result)))
            else:
                self.cover_texture = self.backdrop_texture = None
                self.fade_accent_to(theme.ACCENT)

    def show_artwork(self, url, cover_path, backdrop_path, color):
        if url != self.cover_url:
            return  # the song changed again while this cover was loading
        self.cover_texture = CoreImage(cover_path).texture
        self.backdrop_texture = CoreImage(backdrop_path).texture
        self.fade_accent_to(color or theme.ACCENT)

    def fade_accent_to(self, color):
        Animation.cancel_all(self, "accent")
        Animation(accent=color, d=1.2, t="in_out_quad").start(self)

    def tick_progress(self, *args):
        if self.spotify_state and not self.seeking:
            self.track_position = self.spotify_state.position_now() if self.track_duration else 0

    @staticmethod
    def format_time(ms):
        seconds = int(ms // 1000)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def seek_to(self, position_ms):
        self.track_position = position_ms
        self.spotify.seek(position_ms)

    def toggle_play(self):
        self.spotify.play_pause()

    def next_track(self):
        self.spotify.next()

    def previous_track(self):
        self.spotify.previous()

    # ---- Calls (fake for now) ----

    def start_fake_call(self):
        # Pause the music for the call, but remember whether it was playing.
        self.was_playing_before_call = self.is_playing
        if self.is_playing:
            self.spotify.pause()
        self.caller_name = "Mom"
        self.phone_status = "Incoming: Mom"
        self.call_state = "incoming"

    def answer_call(self):
        self.call_state = "active"
        self.phone_status = f"On call: {self.caller_name}"
        self.call_started = datetime.now()
        self.call_timer = "0:00"
        Clock.schedule_interval(self.tick_call, 1)

    def tick_call(self, dt):
        if self.call_state != "active":
            return False
        seconds = int((datetime.now() - self.call_started).total_seconds())
        self.call_timer = f"{seconds // 60}:{seconds % 60:02d}"

    def end_call(self):
        if self.was_playing_before_call:
            self.spotify.resume()
        self.call_state = "none"
        self.phone_status = "Phone connected"


if __name__ == "__main__":
    HeadUnitApp().run()
