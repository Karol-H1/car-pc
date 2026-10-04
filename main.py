from kivy.app import App
from kivy.core.window import Window
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.screenmanager import NoTransition, Screen, SlideTransition

Window.size = (800, 480)
Window.clearcolor = (0.06, 0.07, 0.09, 1)  # near-black background, easy on the eyes at night

# Stand-in for Spotify until the real music code exists.
FAKE_PLAYLIST = [
    ("Highway Lights", "The Night Drivers"),
    ("Low Tide", "Coastal Radio"),
    ("Engine Hum", "Basement Tapes"),
]


# The looks of these screens live in headunit.kv. Python only needs the class names.
class HomeScreen(Screen):
    pass


class DashcamScreen(Screen):
    pass


class CallScreen(Screen):
    pass


class ReverseScreen(Screen):
    pass


class HeadUnitApp(App):
    # Kivy properties: when one of these changes, every label in the .kv file that
    # uses it redraws automatically.
    track_title = StringProperty(FAKE_PLAYLIST[0][0])
    track_artist = StringProperty(FAKE_PLAYLIST[0][1])
    is_playing = BooleanProperty(True)
    next_turn = StringProperty("In 0.3 mi, turn right onto Main St")
    eta = StringProperty("Arrive 6:42 PM  ·  12 min  ·  5.1 mi")
    phone_status = StringProperty("Phone connected")

    def on_start(self):
        self.track_index = 0
        self.screen_before_reverse = "home"
        self.was_playing_before_call = False
        # Stand-in for the reverse-light wire: the R key flips reverse on and off.
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

    # ---- Music (fake for now) ----

    def toggle_play(self):
        self.is_playing = not self.is_playing

    def next_track(self):
        self.track_index = (self.track_index + 1) % len(FAKE_PLAYLIST)
        self.show_track()

    def previous_track(self):
        self.track_index = (self.track_index - 1) % len(FAKE_PLAYLIST)
        self.show_track()

    def show_track(self):
        self.track_title, self.track_artist = FAKE_PLAYLIST[self.track_index]
        self.is_playing = True

    # ---- Calls (fake for now) ----

    def start_fake_call(self):
        # Pause the music for the call, but remember whether it was playing.
        self.was_playing_before_call = self.is_playing
        self.is_playing = False
        self.phone_status = "Incoming: Mom"
        self.switch_to("call")

    def end_call(self):
        self.is_playing = self.was_playing_before_call
        self.phone_status = "Phone connected"
        self.switch_to("home")


if __name__ == "__main__":
    HeadUnitApp().run()
