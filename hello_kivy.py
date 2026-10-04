from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

# Match a typical 7" car screen so what we see on the laptop is close to the Pi.
Window.size = (800, 480)


class CounterApp(App):
    def build(self):
        self.count = 5

        # Vertical stack: the number on top, the row of buttons below it.
        root = BoxLayout(orientation="horizontal", padding=20, spacing=20)

        self.label = Label(text="5", font_size=200)
        root.add_widget(self.label)

        buttons = BoxLayout(orientation="vertical", spacing=20, size_hint_y=0.3)

        add_button = Button(text="Tap me", font_size=100)
        add_button.bind(on_press=self.add_one)
        buttons.add_widget(add_button)

        reset_button = Button(text="Reset", font_size=150)
        reset_button.bind(on_press=self.reset)
        buttons.add_widget(reset_button)

        root.add_widget(buttons)
        return root

    def add_one(self, button):
        self.count += 1
        self.label.text = str(self.count)

    def reset(self, button):
        self.count = 0
        self.label.text = "0"


if __name__ == "__main__":
    CounterApp().run()
