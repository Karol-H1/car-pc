"""Live traffic: Google Maps from the phone, mirrored onto the head unit with scrcpy.

scrcpy makes a separate virtual screen on the phone, sized for the head unit, starts Google Maps on
it, and shows it in a borderless window placed over the Traffic page, so the phone's own screen stays
free. Needs an Android 10+ phone plugged in by USB with USB debugging allowed, and scrcpy 3+ on the Pi.
Nothing in here touches Kivy; callers hand results to the main thread themselves.
"""
import subprocess
import threading

MAPS_APP = "com.google.android.apps.maps"
WINDOW_TITLE = "Live traffic"  # system/labwc-rules.xml keeps this window on top
SCREEN_DPI = 160               # how big Google Maps draws its buttons and text


def phone_status():
    """Check the phone over adb. Returns (status, model): status is "ready", "unauthorized"
    (plugged in but USB debugging not allowed yet), "missing", or "no-adb" (not installed)."""
    try:
        result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return "no-adb", None
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[1] == "device":
            model = next((p.split(":", 1)[1] for p in parts if p.startswith("model:")), "phone")
            return "ready", model.replace("_", " ")
        if parts[1] == "unauthorized":
            return "unauthorized", None
    return "missing", None


class Mirror:
    def __init__(self, on_exit):
        """on_exit(message) is called from a background thread if scrcpy stops on its own (phone
        unplugged, an error), but not when stop() is called."""
        self.on_exit = on_exit
        self.process = None

    @property
    def running(self):
        return self.process is not None

    def start(self, x, y, width, height):
        """Show the mirror in a window whose top-left corner is at screen pixel (x, y)."""
        if self.running:
            return
        self.process = subprocess.Popen(
            ["scrcpy",
             f"--new-display={width}x{height}/{SCREEN_DPI}", f"--start-app={MAPS_APP}",
             "--no-vd-system-decorations",  # no phone status bar or navigation buttons
             "--no-audio",                  # the phone's sound stays on the phone
             "--max-fps=30", "--video-bit-rate=4M",
             "--window-borderless", f"--window-title={WINDOW_TITLE}",
             f"--window-x={x}", f"--window-y={y}",
             f"--window-width={width}", f"--window-height={height}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        threading.Thread(target=self.watch, args=(self.process,), daemon=True).start()

    def watch(self, process):
        _, errors = process.communicate()
        if process is self.process:  # it stopped by itself, not through stop()
            self.process = None
            last_line = (errors or "").strip().splitlines()[-1:] or ["scrcpy stopped"]
            self.on_exit(last_line[0])

    def stop(self):
        process, self.process = self.process, None
        if process is not None:
            process.terminate()
