"""Geometry helpers underpinning candidate generation."""

from __future__ import annotations

import pytest

from app.core.geo import bearing_delta_deg, detour_ratio, haversine_km, initial_bearing_deg
from app.data.airports import require_airport


def test_haversine_matches_known_distance() -> None:
    amm, ist = require_airport("AMM"), require_airport("IST")
    distance = haversine_km(amm.lat, amm.lon, ist.lat, ist.lon)
    # Published AMM-IST great-circle distance is ~1,190 km.
    assert 1150 < distance < 1250


def test_haversine_is_symmetric_and_zero_on_identity() -> None:
    a, b = require_airport("LHR"), require_airport("JFK")
    assert haversine_km(a.lat, a.lon, b.lat, b.lon) == pytest.approx(
        haversine_km(b.lat, b.lon, a.lat, a.lon)
    )
    assert haversine_km(a.lat, a.lon, a.lat, a.lon) == pytest.approx(0.0, abs=1e-6)


def test_detour_ratio_is_near_one_for_a_collinear_stop() -> None:
    """AMM -> IST -> SKP is a textbook connection: IST is almost exactly en route."""
    amm, ist, skp = (require_airport(code) for code in ("AMM", "IST", "SKP"))
    ab = haversine_km(amm.lat, amm.lon, ist.lat, ist.lon)
    bc = haversine_km(ist.lat, ist.lon, skp.lat, skp.lon)
    ac = haversine_km(amm.lat, amm.lon, skp.lat, skp.lon)
    assert detour_ratio(ab, bc, ac) < 1.15


def test_detour_ratio_rejects_a_backtrack() -> None:
    """AMM -> IST -> DXB doubles back; IST is not "on the way" to Dubai."""
    amm, ist, dxb = (require_airport(code) for code in ("AMM", "IST", "DXB"))
    ab = haversine_km(amm.lat, amm.lon, ist.lat, ist.lon)
    bc = haversine_km(ist.lat, ist.lon, dxb.lat, dxb.lon)
    ac = haversine_km(amm.lat, amm.lon, dxb.lat, dxb.lon)
    assert detour_ratio(ab, bc, ac) > 1.9


def test_detour_ratio_is_infinite_when_origin_equals_destination() -> None:
    assert detour_ratio(500.0, 500.0, 0.0) == float("inf")


def test_bearing_delta_wraps_around_north() -> None:
    assert bearing_delta_deg(350.0, 10.0) == pytest.approx(20.0)
    assert bearing_delta_deg(10.0, 350.0) == pytest.approx(20.0)
    assert bearing_delta_deg(0.0, 180.0) == pytest.approx(180.0)


def test_initial_bearing_points_north_for_due_north_travel() -> None:
    assert initial_bearing_deg(0.0, 0.0, 10.0, 0.0) == pytest.approx(0.0, abs=1e-6)
