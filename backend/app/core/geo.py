"""Great-circle geometry helpers used by the candidate generator.

The hidden-city search is fundamentally a geometric question: *is B on the way
to C?*  These helpers answer that cheaply and without any network calls.
"""

from __future__ import annotations

from math import asin, atan2, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates, in kilometres."""
    p1, p2 = radians(lat1), radians(lat2)
    d_lat = p2 - p1
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(p1) * cos(p2) * sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing from point 1 to point 2, in degrees [0, 360)."""
    p1, p2 = radians(lat1), radians(lat2)
    d_lon = radians(lon2 - lon1)
    x = sin(d_lon) * cos(p2)
    y = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(d_lon)
    return (degrees(atan2(x, y)) + 360.0) % 360.0


def bearing_delta_deg(bearing_a: float, bearing_b: float) -> float:
    """Smallest absolute angle between two bearings, in degrees [0, 180]."""
    delta = abs(bearing_a - bearing_b) % 360.0
    return delta if delta <= 180.0 else 360.0 - delta


def detour_ratio(
    ab_km: float,
    bc_km: float,
    ac_km: float,
) -> float:
    """How much longer A->B->C is than flying A->C directly.

    ``1.0`` means B sits exactly on the great circle between A and C, i.e. a
    perfect connection.  Values grow as B becomes a backtrack.  Returns
    ``inf`` when A and C coincide, since "extending" to your own origin is
    meaningless.
    """
    if ac_km <= 1.0:
        return float("inf")
    return (ab_km + bc_km) / ac_km
