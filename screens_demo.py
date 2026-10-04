from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager, SlideTransition

Window.size = (800, 480)


def build_page(title, buttons, title_color=(1, 1, 1, 1)):
    """A big title with a row of buttons under it. buttons is a list of (text, function) pairs."""
    page = BoxLayout(orientation="vertical", padding=20, spacing=20)
    page.add_widget(Label(text=title, font_size=48, color=title_color, markup=True, halign="center"))

    row = BoxLayout(orientation="horizontal", spacing=20, size_hint_y=0.35)
    for text, function in buttons:
        button = Button(text=text, font_size=32)
        button.bind(on_press=function)
        row.add_widget(button)
    page.add_widget(row)
    return page


class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = App.get_running_app()
        self.add_widget(build_page(
            "Home\n[size=20](press R to toggle reverse)[/size]",
            [
                ("Dashcam", lambda button: app.switch_to("dashcam")),
                ("Fake call", lambda button: app.switch_to("call")),
            ],
        ))


class DashcamScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = App.get_running_app()
        self.add_widget(build_page(
            "Dashcam view",
            [("Back", lambda button: app.switch_to("home"))],
        ))


class CallScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = App.get_running_app()
        self.add_widget(build_page(
            "Incoming call: Mom",
            [
                ("Answer", lambda button: print("Answered")),
                ("Hang up", lambda button: app.switch_to("home")),
            ],
        ))


class ReverseScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # No buttons: this screen leaves on its own when the car shifts out of reverse.
        self.add_widget(build_page("REVERSE CAMERA", [], title_color=(1, 0.3, 0.3, 1)))


class HeadUnitApp(App):
    def build(self):
        self.screen_before_reverse = "home"

        self.manager = ScreenManager(transition=SlideTransition())
        self.manager.add_widget(HomeScreen(name="home"))
        self.manager.add_widget(DashcamScreen(name="dashcam"))
        self.manager.add_widget(CallScreen(name="call"))
        self.manager.add_widget(ReverseScreen(name="reverse"))

        # Stand-in for the reverse-light wire: the R key flips reverse on and off.
        Window.bind(on_key_down=self.on_key_down)
        return self.manager

    def switch_to(self, name, instant=False):
        self.manager.transition = NoTransition() if instant else SlideTransition()
        self.manager.current = name

    # On the Pi, the GPIO code will call these two instead of the keyboard.
    def reverse_on(self):
        if self.manager.current != "reverse":
            self.screen_before_reverse = self.manager.current
            self.switch_to("reverse", instant=True)

    def reverse_off(self):
        if self.manager.current == "reverse":
            self.switch_to(self.screen_before_reverse, instant=True)

    def on_key_down(self, window, key, scancode, codepoint, modifiers):
        if codepoint == "r":
            if self.manager.current == "reverse":
                self.reverse_off()
            else:
                self.reverse_on()


if __name__ == "__main__":
    HeadUnitApp().run()
