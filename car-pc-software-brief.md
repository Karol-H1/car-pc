# Car PC: Software Brief for Claude Code

## Goal
A DIY dash-mounted head unit for a **2011 Honda Civic LX**, replacing a ~$100 Amazon Android unit whose Android Auto broke. Raspberry Pi 5 running a **Python + Kivy** touchscreen UI. **No Android Auto.** Budget for the whole project is under $500.

The owner is new to Python UI work and wants explanations as we go, not just code. Dev workflow: flash with Raspberry Pi Imager (pre-configure Wi-Fi + SSH), then work over SSH from a laptop. A wireless keyboard (bundled with the screen) is a fallback only.

## Hardware (decided)
- Raspberry Pi 5, **4GB** (iRasptek starter kit: case, active cooler, 27W supply, 64GB SD with Pi OS). Plan to swap to an endurance-rated microSD before daily car use.
- 7" HDMI + USB touchscreen (Pi 5-compatible), touch USB plugged **directly** into the Pi
- Powered USB hub for GPS, capture card, dashcam
- USB GPS dongle (~$20, u-blox if possible)
- USB capture card for the rear camera. The existing camera uses a **3.5mm TRRS** connector carrying analog composite video, so the card needs a 3.5mm AV input or adapter cable. Low latency matters.
- Front dashcam: USB webcam-style, mounted on the windshield (not on the enclosure)
- Mini-Box M2-ATX-style automotive DC-DC converter (wide input, 5V out, **delayed-off**), fed from constant 12V
- PC817-based optocoupler module for ignition sensing (isolation from 12V)
- Reverse-light signal: reuse the existing tap from the old head unit, still through isolation, into a GPIO
- v1 enclosure is cardboard (bench use only); a 3D-printed case comes later

## Features the software must deliver
1. **Navigation**: native offline maps for normal driving (no lag). **On-demand** phone mirroring (scrcpy) to show Google Maps for live traffic, launched only when requested and closed afterward.
2. **Spotify**: Spotify Connect client on the Pi; UI shows track/artist, with play/pause/skip controls.
3. **Phone calls**: Bluetooth hands-free; UI shows caller name (needs phone contact sharing/PBAP) or number, plus answer/hang up.
4. **Audio management**: pause (or duck) music when a call starts, resume when it ends.
5. **Rear camera**: auto-switch to the camera feed when reverse is engaged (GPIO high), switch back when it drops.
6. **Front dashcam**: loop recording with auto-overwrite, plus a manual dashcam view screen. Storage budget needs thought (roughly 3-6GB/hour at 1080p).
7. **Safe shutdown**: GPIO watches the ignition-sense line. When ignition goes off, run `shutdown -h now`. The converter's delay-off keeps power alive about 15-20 seconds so the OS halts cleanly.

## UI screens (ScreenManager)
Normal driving (nav + now-playing + phone tiles) → Reverse camera (automatic) → Dashcam view (manual) → Incoming/active call. The original sketch's overlay shows a turn banner, ETA, music card and phone card on the home screen.

## Planned software stack
Kivy UI, librespot (or similar), BlueZ + PipeWire for calls and audio, a small Python daemon for call-state/pause logic, GPIO via libgpiod/gpiozero for ignition + reverse, gpsd for GPS, OpenCV/V4L2 for camera capture, scrcpy for on-demand mirroring.

## Verify before building (stated in planning from memory, not confirmed)
- ~~**Offline nav app on Linux**~~ **Decided (Oct 2026):** custom Kivy map (`navmap.py`, roads drawn from OpenStreetMap data) + Valhalla routing via the `pyvalhalla` pip package. Organic Maps runs on Pi (flatpak) but only as a separate desktop app, not inside our UI; Kivy's MapView needs raster tiles that can't be bulk-downloaded legally. pyvalhalla wheels need **Python 3.12+**, so the Pi needs a Trixie-based Pi OS (Python 3.13), not Bookworm (3.11).
- **librespot metadata**: librespot itself may not expose MPRIS; spotifyd or another Connect client might be the better fit for track info. Spotify Connect needs Premium.
- **Call info on Linux**: HFP caller ID/call state on current Pi OS goes through PipeWire/WirePlumber or oFono, not a `org.bluez.Call` interface as I described. Confirm the correct D-Bus path and how the Pi acts as the hands-free device.
- **Audio hardware gaps**: Pi 5 has **no 3.5mm audio jack**, so the aux-out to the car stereo needs a USB audio adapter. Calls also need a **microphone** (USB mic or an adapter with mic input). Neither is on the parts list yet.
- Which pin of the TRRS camera plug carries video, ground, power.

## Suggested build order
1. Bench: Pi + screen + wall power, Kivy hello-world, ScreenManager skeleton
2. Spotify + Bluetooth calls + audio-pause daemon
3. Navigation + on-demand scrcpy
4. Rear camera capture + reverse-trigger screen switch (simulate GPIO on bench)
5. Dashcam capture + loop recording
6. Ignition-sense + shutdown script (bench PSU, not the car)
7. Kiosk autostart on boot, then car install
8. Burn-in test: weeks of daily use, confirm no storage corruption

## Safety notes
Test all GPIO logic with simulated inputs on the bench before connecting to car wiring. Never feed 12V into a GPIO; always go through the optocoupler. Verify ignition-switched vs. constant wires with a multimeter and fuse every tap.
