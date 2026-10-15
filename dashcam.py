"""Dashcam: loop recording from the USB camera, a live preview for the Dashcam page, and saved clips.

ffmpeg copies the camera's MJPEG video straight into one-minute MKV files (no re-encoding, so the Pi
barely works, and MKV stays readable after a sudden power cut). The same frames go to a small file in
RAM that the Dashcam page shows as the live view. A background thread restarts recording if the
camera reappears, deletes the oldest minutes to stay under the storage limit, and moves the minutes
around a "save clip" press into a folder that's never deleted automatically.
Nothing in here touches Kivy.
"""
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import config

SEGMENT_SECONDS = 60
SAVE_BEFORE_SECONDS = 60   # a saved clip keeps this much from before the button press...
SAVE_AFTER_SECONDS = 30    # ...and this much after it
NAME_FORMAT = "%Y-%m-%d_%H-%M-%S"
RAM_DIR = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
PREVIEW = RAM_DIR / "carpc-dashcam.jpg"
LOG = RAM_DIR / "carpc-dashcam.log"


def find_camera(name):
    """The /dev/video device for the camera whose name contains `name`, or None if it isn't plugged in."""
    devices = Path("/sys/class/video4linux")
    if not devices.is_dir():
        return None
    for device in sorted(devices.glob("video*"), key=lambda path: int(path.name[5:])):
        try:
            device_name = (device / "name").read_text().strip()
            index = (device / "index").read_text().strip()
        except OSError:
            continue
        if name.lower() in device_name.lower() and index == "0":  # index 1+ are metadata nodes
            return f"/dev/{device.name}"
    return None


def segment_start(path):
    try:
        return datetime.strptime(path.stem, NAME_FORMAT).timestamp()
    except ValueError:
        return None


class Dashcam:
    def __init__(self):
        self.loop_dir = config.DASHCAM_DIR / "loop"
        self.saved_dir = config.DASHCAM_DIR / "saved"
        self.loop_dir.mkdir(parents=True, exist_ok=True)
        self.saved_dir.mkdir(parents=True, exist_ok=True)
        self.process = None
        self.recording_since = None
        self.save_windows = []   # (from, until) times whose minutes should be kept
        self.loop_bytes = 0
        self.saved_clips = 0
        self.lock = threading.Lock()
        threading.Thread(target=self.supervise, daemon=True).start()

    @property
    def recording(self):
        return self.process is not None and self.process.poll() is None

    def supervise(self):
        while True:
            if not self.recording:
                self.recording_since = None
                device = find_camera(config.DASHCAM_CAMERA)
                if device:
                    self.start(device)
            self.tidy()
            time.sleep(3)

    def start(self, device):
        PREVIEW.unlink(missing_ok=True)  # no stale frame from an earlier run in the live view
        with open(LOG, "w") as log:
            self.process = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                 "-f", "v4l2", "-input_format", "mjpeg", "-video_size", config.DASHCAM_SIZE,
                 "-framerate", str(config.DASHCAM_FPS), "-i", device,
                 # One-minute recordings, named by their start time.
                 "-map", "0:v", "-c", "copy", "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
                 "-reset_timestamps", "1", "-strftime", "1", str(self.loop_dir / f"{NAME_FORMAT}.mkv"),
                 # The newest frame, for the live view (written whole, so it's never read half-done).
                 "-map", "0:v", "-c", "copy", "-f", "image2", "-update", "1", "-atomic_writing", "1",
                 str(PREVIEW)],
                stdout=subprocess.DEVNULL, stderr=log)
        self.recording_since = time.time()

    def stop(self):
        process, self.process = self.process, None
        if process is not None:
            process.terminate()

    def save_clip(self):
        now = time.time()
        with self.lock:
            self.save_windows.append((now - SAVE_BEFORE_SECONDS, now + SAVE_AFTER_SECONDS))

    def tidy(self):
        """Keep saved minutes, and delete the oldest loop minutes when over the storage limit."""
        segments = sorted(self.loop_dir.glob("*.mkv"))
        finished = segments[:-1] if self.recording else segments  # the newest is still being written
        now = time.time()
        with self.lock:
            windows = list(self.save_windows)
            # Forget windows once every minute they touch has been dealt with.
            self.save_windows = [w for w in windows if w[1] > now - SEGMENT_SECONDS]
        for segment in finished:
            start = segment_start(segment)
            if start is not None and any(start < until and start + SEGMENT_SECONDS > since
                                         for since, until in windows):
                shutil.move(str(segment), self.saved_dir / segment.name)

        segments = sorted(self.loop_dir.glob("*.mkv"))
        sizes = {segment: segment.stat().st_size for segment in segments if segment.exists()}
        total = sum(sizes.values())
        limit = config.DASHCAM_MAX_GB * 1e9
        min_free = config.DASHCAM_MIN_FREE_GB * 1e9
        for segment in segments[:-1]:  # never the one being written
            if total <= limit and shutil.disk_usage(self.loop_dir).free >= min_free:
                break
            total -= sizes.get(segment, 0)
            segment.unlink(missing_ok=True)
        self.loop_bytes = total
        self.saved_clips = len(list(self.saved_dir.glob("*.mkv")))
