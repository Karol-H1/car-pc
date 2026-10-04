"""Small geography helpers: map projection, distances, and formatting."""
import math

EARTH_RADIUS = 6378137.0
METERS_PER_MILE = 1609.344
FEET_PER_METER = 3.28084


def to_world(lat, lon):
    """Latitude/longitude to Web Mercator meters (x grows east, y grows north)."""
    x = math.radians(lon) * EARTH_RADIUS
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * EARTH_RADIUS
    return x, y


def to_latlon(x, y):
    """The reverse of to_world."""
    lon = math.degrees(x / EARTH_RADIUS)
    lat = math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi / 2)
    return lat, lon


def distance_m(lat1, lon1, lat2, lon2):
    """Straight-line distance in meters between two points (haversine formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Compass direction from point 1 to point 2: 0 = north, 90 = east."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360


def decode_polyline(encoded, precision=6):
    """Decode a Valhalla route shape (Google's polyline format, 6 decimal places) into (lat, lon) pairs."""
    points = []
    index = lat = lon = 0
    factor = 10 ** precision
    while index < len(encoded):
        for axis in (0, 1):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        points.append((lat / factor, lon / factor))
    return points


def format_distance(meters):
    """US-style distance for the turn banner: feet when close, miles otherwise."""
    miles = meters / METERS_PER_MILE
    if miles < 0.1:
        feet = meters * FEET_PER_METER
        return f"{max(50, round(feet / 50) * 50)} ft"
    if miles < 10:
        return f"{miles:.1f} mi"
    return f"{miles:.0f} mi"
