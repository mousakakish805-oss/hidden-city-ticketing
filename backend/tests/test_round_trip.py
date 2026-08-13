"""Return trips.

A return trip is priced as **two separate one-way tickets**, never as one
round-trip fare. That is not a shortcut -- it is the only structure in which
hidden-city ticketing works at all. Miss a leg on a round-trip ticket and the
airline cancels every leg after it, including the flight home. The disclaimer
tells users to buy two one-ways; the search prices exactly that.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

DEPART = (date.today() + timedelta(days=45)).isoformat()
RETURN = (date.today() + timedelta(days=52)).isoformat()


def body(**overrides) -> dict:
    return {
        "origin": "AMM",
        "destination": "IST",
        "departure_date": DEPART,
        **overrides,
    }


# ---------------------------------------------------------------- one-way


async def test_one_way_is_still_the_default(client: AsyncClient) -> None:
    result = (
        await client.post("/api/search", params={"wait": "true"}, json=body())
    ).json()

    assert result["trip_type"] == "one_way"
    assert result["inbound"] is None
    assert result["totals"] is None


async def test_one_way_response_shape_is_unchanged(client: AsyncClient) -> None:
    """Adding return trips must not break anything reading the old shape."""
    result = (
        await client.post("/api/search", params={"wait": "true"}, json=body())
    ).json()

    for key in ("baseline", "hidden_city", "candidates", "probes", "price_matrix"):
        assert key in result, f"top-level '{key}' disappeared"
    assert result["baseline"]["price"] > 0


# -------------------------------------------------------------- round trip


async def test_round_trip_prices_both_directions(client: AsyncClient) -> None:
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    assert result["trip_type"] == "round_trip"
    assert result["outbound"] is not None
    assert result["inbound"] is not None

    outbound, inbound = result["outbound"], result["inbound"]
    assert (outbound["origin"], outbound["destination"]) == ("AMM", "IST")
    # The return flies the same pair backwards, on the return date.
    assert (inbound["origin"], inbound["destination"]) == ("IST", "AMM")
    assert outbound["departure_date"] == DEPART
    assert inbound["departure_date"] == RETURN


async def test_each_direction_is_analysed_independently(client: AsyncClient) -> None:
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    for leg in (result["outbound"], result["inbound"]):
        assert leg["baseline"]["price"] > 0
        assert leg["candidates"], "each direction needs its own candidate list"
        assert "hidden_city" in leg
        assert "price_matrix" in leg


async def test_return_candidates_are_beyond_the_return_destination(
    client: AsyncClient,
) -> None:
    """Coming home from IST, the onward cities lie beyond AMM -- not beyond IST."""
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    inbound_codes = {c["iata"] for c in result["inbound"]["candidates"]}
    outbound_codes = {c["iata"] for c in result["outbound"]["candidates"]}

    assert inbound_codes
    assert inbound_codes != outbound_codes
    # Never propose the trip's own endpoints as a ticketed destination.
    assert not ({"AMM", "IST"} & inbound_codes)


async def test_every_offer_on_both_legs_is_one_way(client: AsyncClient) -> None:
    """The critical invariant: a hidden-city fare on a round-trip ticket would
    cancel the traveller's flight home."""
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    for leg in (result["outbound"], result["inbound"]):
        for offer in leg["baseline"]["offers"]:
            assert len(offer["itineraries"]) == 1, "a second itinerary means a return leg"
        for option in leg["hidden_city"]["options"]:
            assert len(option["offer"]["itineraries"]) == 1


async def test_totals_add_the_two_tickets(client: AsyncClient) -> None:
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    totals = result["totals"]
    expected_baseline = (
        result["outbound"]["baseline"]["price"] + result["inbound"]["baseline"]["price"]
    )

    assert totals["baseline"] == pytest.approx(expected_baseline, abs=0.02)
    assert totals["best"] <= totals["baseline"]
    assert totals["savings"] == pytest.approx(totals["baseline"] - totals["best"], abs=0.02)
    assert totals["currency"] == "USD"


async def test_totals_use_the_hidden_fare_only_where_one_exists(
    client: AsyncClient,
) -> None:
    """A traveller can take the hidden-city option on one leg and a normal
    fare on the other; the total must reflect exactly that."""
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    totals = result["totals"]
    legs_with_options = sum(
        1 for leg in (result["outbound"], result["inbound"]) if leg["hidden_city"]["count"]
    )

    assert totals["legs_with_savings"] == legs_with_options
    if legs_with_options == 0:
        assert totals["savings"] == pytest.approx(0.0, abs=0.02)
    else:
        assert totals["savings"] > 0


async def test_disclaimer_is_shared_not_duplicated(client: AsyncClient) -> None:
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    assert "disclaimer" in result
    assert "disclaimer" not in result["outbound"]
    assert "disclaimer" not in result["inbound"]


# -------------------------------------------------------------- validation


async def test_return_before_departure_is_rejected(client: AsyncClient) -> None:
    earlier = (date.today() + timedelta(days=10)).isoformat()

    response = await client.post(
        "/api/search", params={"wait": "true"}, json=body(return_date=earlier)
    )

    assert response.status_code == 422


async def test_same_day_return_is_allowed(client: AsyncClient) -> None:
    """Unusual but legitimate -- a day trip is a real thing people book."""
    response = await client.post(
        "/api/search", params={"wait": "true"}, json=body(return_date=DEPART)
    )

    assert response.status_code == 200
    assert response.json()["trip_type"] == "round_trip"


async def test_return_beyond_a_year_is_rejected(client: AsyncClient) -> None:
    far = (date.today() + timedelta(days=400)).isoformat()

    response = await client.post(
        "/api/search", params={"wait": "true"}, json=body(return_date=far)
    )

    assert response.status_code == 422


async def test_return_date_is_persisted(client: AsyncClient) -> None:
    result = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=body(return_date=RETURN)
        )
    ).json()

    replayed = (await client.get(f"/api/search/{result['search_id']}")).json()

    assert replayed["trip_type"] == "round_trip"
    assert replayed["inbound"]["departure_date"] == RETURN


async def test_round_trip_costs_two_fan_outs(client: AsyncClient) -> None:
    """Worth asserting: on a metered plan this doubles the API spend."""
    one_way = (
        await client.post("/api/search", params={"wait": "true"}, json=body(refresh=True))
    ).json()
    both = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json=body(return_date=RETURN, refresh=True),
        )
    ).json()

    assert len(both["outbound"]["probes"]) + len(both["inbound"]["probes"]) > len(
        one_way["probes"]
    )
