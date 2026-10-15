"""The Pi's output volume, through PipeWire's wpctl (for the volume slider on the Music page).

In the car, the stereo's knob is the main volume control: leave this fairly high (80-100%) so the
aux input gets a strong, clean signal. Nothing in here touches Kivy.
"""
import re
import shutil
import subprocess

SINK = "@DEFAULT_AUDIO_SINK@"


def available():
    return shutil.which("wpctl") is not None


def get_volume():
    """Current output volume from 0 to 1, or None if it can't be read."""
    try:
        output = subprocess.run(["wpctl", "get-volume", SINK], capture_output=True, text=True,
                                timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"Volume:\s*([\d.]+)", output)
    return min(1.0, float(match.group(1))) if match else None


def set_volume(volume):
    try:
        subprocess.run(["wpctl", "set-volume", SINK, f"{max(0.0, min(1.0, volume)):.2f}"],
                       capture_output=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass
