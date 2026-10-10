"""Find out how the touchscreen reaches SDL apps like scrcpy (diagnostic, run on the Pi).

Shows a full-screen color and records what SDL receives: real finger touches (needed for pinch) or
only an emulated mouse. Run once per display system:
    SDL_VIDEODRIVER=x11 python tools/touch_test.py blue
    SDL_VIDEODRIVER=wayland python tools/touch_test.py green
The test starts at the first press (not just the pointer moving) and ends 20 seconds later, or
after 15 minutes with no press.
Needs: pip install pysdl2
"""
import ctypes
import os
import sys
import time

import sdl2

COLORS = {"blue": (20, 60, 200), "green": (20, 150, 60)}
TEST_SECONDS = 20
WAIT_SECONDS = 15 * 60


def main():
    color = COLORS[sys.argv[1] if len(sys.argv) > 1 else "blue"]
    driver = os.environ.get("SDL_VIDEODRIVER", "default")
    sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO)
    window = sdl2.SDL_CreateWindow(b"touch test", 0, 0, 800, 480,
                                   sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP | sdl2.SDL_WINDOW_BORDERLESS)
    surface = sdl2.SDL_GetWindowSurface(window)
    sdl2.SDL_FillRect(surface, None, sdl2.SDL_MapRGB(surface.contents.format, *color))
    sdl2.SDL_UpdateWindowSurface(window)

    started = time.time()
    first_touch = None
    fingers, max_fingers = set(), 0
    counts = {"finger_down": 0, "finger_motion": 0, "mouse_from_touch": 0, "real_mouse": 0}
    event = sdl2.SDL_Event()
    while True:
        now = time.time()
        if first_touch and now - first_touch > TEST_SECONDS:
            break
        if not first_touch and now - started > WAIT_SECONDS:
            break
        while sdl2.SDL_PollEvent(ctypes.byref(event)):
            kind = event.type
            if kind == sdl2.SDL_QUIT:
                first_touch, started = 0.0, 0.0  # asked to close: finish right away
                continue
            if kind == sdl2.SDL_FINGERDOWN:
                counts["finger_down"] += 1
                fingers.add(event.tfinger.fingerId)
                max_fingers = max(max_fingers, len(fingers))
            elif kind == sdl2.SDL_FINGERUP:
                fingers.discard(event.tfinger.fingerId)
            elif kind == sdl2.SDL_FINGERMOTION:
                counts["finger_motion"] += 1
            elif kind in (sdl2.SDL_MOUSEBUTTONDOWN, sdl2.SDL_MOUSEMOTION):
                which = event.button.which if kind == sdl2.SDL_MOUSEBUTTONDOWN else event.motion.which
                counts["mouse_from_touch" if which == sdl2.SDL_TOUCH_MOUSEID else "real_mouse"] += 1
            else:
                continue
            if kind in (sdl2.SDL_FINGERDOWN, sdl2.SDL_MOUSEBUTTONDOWN):
                first_touch = first_touch or time.time()
        sdl2.SDL_Delay(5)

    sdl2.SDL_DestroyWindow(window)
    sdl2.SDL_Quit()
    print(f"driver={driver} touched={first_touch is not None} most_fingers_at_once={max_fingers} {counts}")


if __name__ == "__main__":
    main()
