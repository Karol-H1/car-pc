"""Spotify through go-librespot, the Spotify Connect receiver running on the Pi.

go-librespot makes the Pi show up as a speaker ("Civic") in the Spotify app. Its local API tells us
what's playing (a websocket of events) and takes play/pause/skip commands (HTTP POSTs).
Nothing in here touches Kivy; callers hand results to the main thread themselves.
"""
import json
import threading
import time
import urllib.request
from dataclasses import dataclass, replace

import websocket  # the websocket-client package

API = "http://127.0.0.1:3678"  # where go-librespot listens (system/go-librespot/config.yml)
RECONNECT_SECONDS = 5


@dataclass(frozen=True)
class SpotifyState:
    connected: bool = False  # go-librespot is running and reachable
    active: bool = False     # a phone has picked this device in the Spotify app
    playing: bool = False
    title: str = ""
    artist: str = ""
    cover_url: str = ""
    duration: int = 0        # milliseconds
    # go-librespot only reports the position when something happens (new track, seek, pause), so
    # remember the last report and when it came; position_now() works out the rest.
    position: int = 0        # milliseconds
    position_at: float = 0.0  # time.monotonic() of that report

    def position_now(self):
        if not self.playing:
            return self.position
        elapsed = (time.monotonic() - self.position_at) * 1000
        return min(self.duration, self.position + elapsed)


class Spotify:
    def __init__(self, on_change):
        """on_change(SpotifyState) is called from a background thread whenever anything changes."""
        self.on_change = on_change
        self.state = None  # unknown until the first check, which is always reported
        threading.Thread(target=self.listen, daemon=True).start()

    # ---------- Controls (sent on a background thread so a slow reply never freezes the screen) ----------

    def play_pause(self):
        self.send("/player/playpause")

    def pause(self):
        self.send("/player/pause")

    def resume(self):
        self.send("/player/resume")

    def next(self):
        self.send("/player/next")

    def previous(self):
        self.send("/player/prev")

    def seek(self, position_ms):
        self.send("/player/seek", {"position": int(position_ms)})

    def send(self, path, body=None):
        threading.Thread(target=self.post, args=(path, body), daemon=True).start()

    def post(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else b""
        request = urllib.request.Request(API + path, data=data, method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(request, timeout=3)
        except OSError as error:
            print(f"Spotify: {path} failed: {error}")

    # ---------- Following playback ----------

    def update(self, **changes):
        new_state = replace(self.state or SpotifyState(), **changes)
        if new_state != self.state:
            self.state = new_state
            self.on_change(new_state)

    def listen(self):
        """Background thread: stay connected to go-librespot's event stream, reconnecting if it drops."""
        while True:
            try:
                self.load_status()
                events = websocket.create_connection(API.replace("http", "ws", 1) + "/events")
                while True:
                    self.handle(json.loads(events.recv()))
            except (OSError, websocket.WebSocketException, ValueError):
                self.update(connected=False, active=False, playing=False)
                time.sleep(RECONNECT_SECONDS)

    def load_status(self):
        """Catch up on what's playing right now (used on startup and after reconnecting)."""
        with urllib.request.urlopen(API + "/status", timeout=3) as response:
            body = response.read()
        if response.status == 204 or not body:  # running, but no phone has connected yet
            self.update(connected=True, active=False, playing=False)
            return
        status = json.loads(body)
        track = status.get("track") or {}
        self.update(connected=True, active=True,
                    playing=not (status.get("paused") or status.get("stopped")),
                    title=track.get("name", ""),
                    artist=", ".join(track.get("artist_names") or []),
                    cover_url=track.get("album_cover_url") or "",
                    duration=track.get("duration", 0), position=track.get("position", 0),
                    position_at=time.monotonic())

    def handle(self, event):
        kind, data = event.get("type"), event.get("data") or {}
        now = time.monotonic()
        if kind == "metadata":
            self.update(active=True, title=data.get("name", ""),
                        artist=", ".join(data.get("artist_names") or []),
                        cover_url=data.get("album_cover_url") or "",
                        duration=data.get("duration", 0), position=data.get("position", 0),
                        position_at=now)
        elif kind == "seek":
            self.update(position=data.get("position", 0), position_at=now)
        elif kind == "active":
            self.update(active=True)
        elif kind == "inactive":
            self.update(active=False, playing=False)
        elif kind == "playing":
            if not self.state.playing:
                # Carry on from wherever the position was frozen when playback paused.
                self.update(playing=True, position_at=now)
        elif kind in ("paused", "not_playing", "stopped"):
            if self.state.playing:
                self.update(playing=False, position=int(self.state.position_now()), position_at=now)
