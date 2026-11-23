"""Unit tests for photosphere.media.gps."""

from __future__ import annotations

from photosphere.media.gps import dms_to_decimal, encode_geohash


def test_gps_dms_to_decimal_and_geohash() -> None:
    lat = dms_to_decimal(45.0, 27.0, 51.12, "N")
    lon = dms_to_decimal(9.0, 11.0, 24.0, "E")
    geohash = encode_geohash(lat, lon)
    assert geohash.startswith("u0nd9")

    assert dms_to_decimal(10.0, 30.0, 0.0, "S") == -10.5
    assert dms_to_decimal(20.0, 30.0, 0.0, "W") == -20.5
