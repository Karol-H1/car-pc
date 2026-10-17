"""The look of the head unit: colors, fonts, icons, and generated textures used by every screen.

Fonts: Rajdhani (SIL Open Font License) for numbers and UI labels; Roboto, Kivy's built-in font, for
song titles and street names because it also covers non-Latin alphabets. Icons: Google's Material
Icons Round (Apache 2.0). Licenses are next to the files in assets/fonts.
"""
import colorsys
from pathlib import Path

import numpy as np
from kivy.core.text import LabelBase
from kivy.graphics.texture import Texture

FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
LabelBase.register("Display", fn_regular=str(FONTS / "Rajdhani-SemiBold.ttf"),
                   fn_bold=str(FONTS / "Rajdhani-Bold.ttf"))
LabelBase.register("Icons", fn_regular=str(FONTS / "MaterialIconsRound-Regular.otf"))

# ---------- Colors ----------
BACKGROUND = (0.027, 0.031, 0.047, 1)
GLASS = (1, 1, 1, 0.055)        # card fill, over the glowing background
GLASS_STRONG = (0.06, 0.07, 0.1, 0.88)  # floating cards over the map: need to stay readable
EDGE = (1, 1, 1, 0.085)         # thin card outline
TEXT = (0.95, 0.96, 0.98, 1)
MUTED = (0.62, 0.66, 0.74, 1)
DIM = (0.40, 0.44, 0.52, 1)
ACCENT = (0.24, 0.78, 1.0, 1)   # default; the album cover's color takes over while music plays
GOOD = (0.18, 0.84, 0.48, 1)
DANGER = (1.0, 0.29, 0.36, 1)
WARNING = (1.0, 0.76, 0.24, 1)

# ---------- Icons (Material Icons Round code points) ----------
_CODES = {
    "add": "e145", "bluetooth": "e1a7", "call": "e0b0", "call_end": "e0b1", "camera_rear": "e3b2",
    "cast": "e307", "close": "e5cd", "directions_boat": "e532", "directions_car": "e531",
    "equalizer": "e01d", "explore": "e87a", "fiber_manual_record": "e061", "flag": "e153",
    "fork_left": "eba0", "fork_right": "ebac", "gps_fixed": "e1b3", "gps_not_fixed": "e1b4", "gps_off": "e1b5",
    "graphic_eq": "e1b8", "headphones": "f01f", "home": "e88a", "library_music": "e030",
    "location_on": "e0c8", "map": "e55b", "merge": "eb98", "mic": "e029", "music_note": "e405",
    "my_location": "e55c", "navigation": "e55d", "near_me": "e569", "pause": "e034", "person": "e7fd", "phone_android": "e324", "backspace": "e14a", "call_made": "e0b2",
    "call_missed": "e0b4", "call_received": "e0b5", "contacts": "e0ba", "dialpad": "e0bc",
    "history": "e889", "phone_in_talk": "e61d", "volume_down": "e04d", "volume_mute": "e04e",
    "pause_circle": "e1a2", "stop": "e047",
    "phone": "e0cd", "play_arrow": "e037", "ramp_left": "eb9c", "ramp_right": "eb96", "remove": "e15b",
    "roundabout_left": "eb99", "roundabout_right": "eba3", "sd_storage": "e1c2", "settings": "e8b8",
    "skip_next": "e044", "skip_previous": "e045", "speed": "e9e4", "sports_score": "f06e",
    "straight": "eb95", "touch_app": "e913", "traffic": "e565", "turn_left": "eba6",
    "turn_right": "ebab", "turn_sharp_left": "eba7", "turn_sharp_right": "ebaa",
    "turn_slight_left": "eba4", "turn_slight_right": "eb9a", "u_turn_left": "eba1",
    "u_turn_right": "eba2", "videocam": "e04b", "volume_up": "e050", "warning": "e002",
    "wifi": "e63e", "wifi_off": "e648",
}
ICONS = {name: chr(int(code, 16)) for name, code in _CODES.items()}

# Valhalla maneuver type numbers -> turn arrow for the turn card.
MANEUVER_ICONS = {
    1: "straight", 2: "turn_right", 3: "turn_left", 4: "sports_score", 5: "sports_score",
    6: "sports_score", 7: "straight", 8: "straight", 9: "turn_slight_right", 10: "turn_right",
    11: "turn_sharp_right", 12: "u_turn_right", 13: "u_turn_left", 14: "turn_sharp_left",
    15: "turn_left", 16: "turn_slight_left", 17: "straight", 18: "ramp_right", 19: "ramp_left",
    20: "ramp_right", 21: "ramp_left", 22: "straight", 23: "fork_right", 24: "fork_left",
    25: "merge", 26: "roundabout_right", 27: "roundabout_right", 28: "directions_boat",
    29: "directions_boat", 37: "merge", 38: "merge",
}


def with_alpha(color, alpha):
    return (*color[:3], alpha)


def shift_hue(color, degrees, saturation=1.0, value=1.0):
    """A related color for the background glow: same family, turned around the color wheel."""
    h, s, v = colorsys.rgb_to_hsv(*color[:3])
    r, g, b = colorsys.hsv_to_rgb((h + degrees / 360) % 1, min(1, s * saturation), min(1, v * value))
    return (r, g, b, color[3] if len(color) > 3 else 1)


# ---------- Generated textures (made once, after the window exists) ----------
_textures = {}


def glow_texture(size=256):
    """A soft white dot that fades to transparent at its edge. Tinted with a Color, it makes glows."""
    if "glow" not in _textures:
        y, x = np.mgrid[-1:1:size * 1j, -1:1:size * 1j]
        alpha = np.clip(1 - np.sqrt(x * x + y * y), 0, 1) ** 2.2
        pixels = np.dstack([np.full_like(alpha, 255)] * 3 + [alpha * 255]).astype(np.uint8)
        texture = Texture.create(size=(size, size), colorfmt="rgba")
        texture.blit_buffer(pixels.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
        _textures["glow"] = texture
    return _textures["glow"]


def fade_texture(size=128):
    """Transparent at the top, solid at the bottom (stretched over things to darken them)."""
    if "fade" not in _textures:
        alpha = np.linspace(255, 0, size)[:, None]  # textures start at the bottom row
        pixels = np.dstack([np.zeros_like(alpha)] * 3 + [alpha]).astype(np.uint8)
        texture = Texture.create(size=(1, size), colorfmt="rgba")
        texture.blit_buffer(pixels.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
        _textures["fade"] = texture
    return _textures["fade"]
