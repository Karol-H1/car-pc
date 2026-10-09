from datetime import datetime, timedelta

from kivy.config import Config

import config

if config.ON_PI:
    # The touchscreen reaches Kivy twice: as real multitouch from the kernel (the probesysfs
    # provider) and as a mouse the desktop emulates from the same finger. Keep only the real one.
    Config.remove_option("input", "mouse")
else:
    # Without this, right-clicking on a laptop leaves red "fake finger" dots for multitouch testing.
    Config.set("input", "mouse", "mouse,multitouch_on_demand")

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.properties import BooleanProperty, NumericProperty, StringProperty  # noqa: E402
from kivy.uix.screenmanager import NoTransition, Screen, SlideTransition  # noqa: E402
from kivy.uix.slider import Slider  # noqa: E402

import geo  # noqa: E402
import navmap  # noqa: E402,F401  (registers NavMap so headunit.kv can use it)
from demo_drive import DemoDrive  # noqa: E402
from navigation import OFF_ROUTE_METERS, Navigator  # noqa: E402
from spotify import Spotify  # noqa: E402

if config.ON_PI:
    Window.fullscreen = "auto"  # cover the taskbar; the car screen is the whole display
else:
    Window.size = (800, 480)  # the Pi's screen size, for laptop testing
Window.clearcolor = (0.06, 0.07, 0.09, 1)  # near-black background, easy on the eyes at night

NO_ROUTE_TEXT = "Hold the map to choose a destination"


# The looks of these screens live in headunit.kv. Python only needs the class names.
class HomeScreen(Screen):
    pass


class DashcamScreen(Screen):
    pass


class CallScreen(Screen):
    pass


class ReverseScreen(Screen):
    pass


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


class HeadUnitApp(App):
    # Kivy properties: when one of these changes, every label in the .kv file that
    # uses it redraws automatically.
    track_title = StringProperty("Spotify")
    track_artist = StringProperty("Connecting...")
    album_cover = StringProperty("")
    is_playing = BooleanProperty(False)
    track_position = NumericProperty(0)  # milliseconds
    track_duration = NumericProperty(0)
    next_turn = StringProperty(NO_ROUTE_TEXT)
    eta = StringProperty("No route")
    has_route = BooleanProperty(False)
    phone_status = StringProperty("Phone connected")

    def on_start(self):
        self.screen_before_reverse = "home"
        self.was_playing_before_call = False

        self.navigator = Navigator()
        self.route = None
        self.destination = None
        self.rerouting = False
        self.demo = None
        self.map = self.root.get_screen("home").ids.navmap
        self.car_position = config.DEFAULT_POSITION
        self.map.set_car(*self.car_position, 0)

        self.spotify = Spotify(lambda state: Clock.schedule_once(lambda dt: self.show_spotify(state)))
        self.spotify_state = None
        self.seek_bar = self.root.get_screen("home").ids.seek_bar
        Clock.schedule_interval(self.tick_progress, 0.5)

        # Keyboard stand-ins while testing on the laptop:
        #   R = reverse-light wire on/off, D = start a demo drive along the current route.
        Window.bind(on_key_down=self.on_key_down)

    # ---- Screens ----

    def switch_to(self, name, instant=False):
        self.root.transition = NoTransition() if instant else SlideTransition()
        self.root.current = name

    def reverse_on(self):
        if self.root.current != "reverse":
            self.screen_before_reverse = self.root.current
            self.switch_to("reverse", instant=True)

    def reverse_off(self):
        if self.root.current == "reverse":
            self.switch_to(self.screen_before_reverse, instant=True)

    def on_key_down(self, window, key, scancode, codepoint, modifiers):
        if codepoint == "r":
            if self.root.current == "reverse":
                self.reverse_off()
            else:
                self.reverse_on()
        elif codepoint == "d":
            self.start_demo_drive()

    # ---- Navigation ----

    def navigate_to(self, lat, lon):
        self.destination = (lat, lon)
        self.next_turn = "Finding route..."
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
            self.next_turn = "No route found. Hold the map to try another spot"
            return
        self.route = route
        self.has_route = True
        self.map.set_route(route.world)
        if show_overview:
            self.map.show_overview(route.world)
        self.update_guidance()

    def cancel_route(self):
        self.route = self.destination = None
        self.has_route = False
        if self.demo:
            self.demo.stop()
        self.map.set_route([])
        self.next_turn = NO_ROUTE_TEXT
        self.eta = "No route"

    def start_demo_drive(self):
        if self.route is None:
            return
        if self.demo:
            self.demo.stop()
        self.route.last_index = 0
        self.demo = DemoDrive(self.route, self.on_position, config.DEMO_SPEED)
        self.map.recenter()

    def on_position(self, lat, lon, heading):
        """Called with every new position: from the demo drive now, from the GPS later."""
        self.car_position = (lat, lon)
        self.map.set_car(lat, lon, heading)
        self.update_guidance()

    def update_guidance(self):
        if self.route is None:
            return
        progress = self.route.progress(*self.car_position)
        if progress.arrived:
            self.cancel_route()
            self.next_turn = "You have arrived"
            return
        if progress.off_route > OFF_ROUTE_METERS and not self.rerouting:
            self.rerouting = True
            self.next_turn = "Rerouting..."
            self.plan_route()
            return
        self.next_turn = f"{geo.format_distance(progress.to_maneuver)}  ·  {progress.instruction}"
        arrival = (datetime.now() + timedelta(seconds=progress.time_left)).strftime("%I:%M %p").lstrip("0")
        minutes = max(1, round(progress.time_left / 60))
        self.eta = (f"Arrive {arrival}  ·  {minutes} min  ·  "
                    f"{progress.remaining / geo.METERS_PER_MILE:.1f} mi")

    # ---- Music (Spotify) ----

    def show_spotify(self, state):
        if not state.connected:
            self.track_title, self.track_artist = "Spotify", "Not running"
        elif not state.active or not state.title:
            self.track_title, self.track_artist = "Nothing playing", "Pick \"Civic\" in the Spotify app"
        else:
            self.track_title, self.track_artist = state.title, state.artist
        self.album_cover = state.cover_url if state.active else ""
        self.is_playing = state.playing
        self.spotify_state = state
        self.track_duration = state.duration if state.active else 0
        self.tick_progress()

    def tick_progress(self, *args):
        if self.spotify_state and not self.seek_bar.dragging:
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
        self.phone_status = "Incoming: Mom"
        self.switch_to("call")

    def end_call(self):
        if self.was_playing_before_call:
            self.spotify.resume()
        self.phone_status = "Phone connected"
        self.switch_to("home")


if __name__ == "__main__":
    HeadUnitApp().run()
