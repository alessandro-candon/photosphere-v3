"""Geohash encoding and EXIF DMS coordinate conversion ported from photosphere-v2."""

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_BITS = (16, 8, 4, 2, 1)


def _narrow_interval(
    interval: tuple[float, float], value: float, bit_mask: int, ch: int
) -> tuple[tuple[float, float], int]:
    mid = (interval[0] + interval[1]) / 2.0
    if value > mid:
        return (mid, interval[1]), ch | bit_mask
    return (interval[0], mid), ch


def encode_geohash(latitude: float, longitude: float, precision: int = 9) -> str:
    """Encode WGS84 latitude/longitude into a base-32 geohash string."""
    lat_interval = (-90.0, 90.0)
    lon_interval = (-180.0, 180.0)
    chars: list[str] = []
    bit = 0
    ch = 0
    even = True

    while len(chars) < precision:
        if even:
            lon_interval, ch = _narrow_interval(lon_interval, longitude, _BITS[bit], ch)
        else:
            lat_interval, ch = _narrow_interval(lat_interval, latitude, _BITS[bit], ch)
        even = not even
        if bit < 4:
            bit += 1
        else:
            chars.append(_BASE32[ch])
            bit = 0
            ch = 0

    return "".join(chars)


def dms_to_decimal(
    degrees: float,
    minutes: float,
    seconds: float,
    direction: str,
) -> float:
    """Convert EXIF degrees/minutes/seconds with hemisphere ref to decimal degrees."""
    decimal = float(degrees) + float(minutes) / 60.0 + float(seconds) / 3600.0
    if direction.upper() in {"S", "W"}:
        decimal = -decimal
    return decimal
