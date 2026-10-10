"""Album covers: download each one once, make a blurred copy for backgrounds, and pick its most
vivid color so the whole screen can match the music. Runs on a background thread.
"""
import colorsys
import hashlib
import io
import threading
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter

CACHE = Path.home() / ".cache" / "carpc" / "art"


def prepare(url, on_ready):
    """on_ready(url, cover_path, backdrop_path, color or None) is called from a background thread."""
    threading.Thread(target=_prepare, args=(url, on_ready), daemon=True).start()


def _prepare(url, on_ready):
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(url.encode()).hexdigest()[:16]
        cover_path, backdrop_path = CACHE / f"{key}.jpg", CACHE / f"{key}-blur.jpg"
        if not cover_path.exists():
            with urllib.request.urlopen(url, timeout=10) as response:
                image = Image.open(io.BytesIO(response.read())).convert("RGB")
            image.thumbnail((320, 320))
            image.save(cover_path, quality=90)
        image = Image.open(cover_path).convert("RGB")
        if not backdrop_path.exists():
            # Shrinking first makes the blur cheap and extra smooth.
            blurred = image.resize((40, 40)).filter(ImageFilter.GaussianBlur(4))
            blurred.resize((320, 320), Image.BILINEAR).save(backdrop_path, quality=85)
        on_ready(url, str(cover_path), str(backdrop_path), vivid_color(image))
    except (OSError, ValueError) as error:
        print(f"Artwork: couldn't prepare {url}: {error}")


def vivid_color(image):
    """The cover's most eye-catching color as (r, g, b, 1), brightened enough to glow on a dark
    screen. Returns None for black-and-white covers."""
    small = image.resize((40, 40))
    buckets = {}  # hue slice -> (total weight, weighted r, g, b)
    for r, g, b in small.getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        weight = (s * v) ** 2  # colorful and bright pixels count most
        if weight < 0.02:
            continue
        key = int(h * 24)
        total, sr, sg, sb = buckets.get(key, (0, 0, 0, 0))
        buckets[key] = (total + weight, sr + r * weight, sg + g * weight, sb + b * weight)
    if not buckets:
        return None
    total, sr, sg, sb = max(buckets.values())
    if total < 2:
        return None
    h, s, v = colorsys.rgb_to_hsv(sr / total / 255, sg / total / 255, sb / total / 255)
    r, g, b = colorsys.hsv_to_rgb(h, min(0.85, max(0.5, s)), max(0.9, v))
    return (r, g, b, 1)
