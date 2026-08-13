"""RapidAPI (Air Scraper) provider.

Written against the documented Skyscanner-derived shape. This listing is an
unofficial scraper whose payload changes without notice, so these tests pin the
behaviour that matters and `scripts/probe_rapidapi.py` verifies the shape
against a real key.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import httpx
import pytest

from app.providers.base import ProviderError, SearchRequest
from app.providers.rapidapi import RapidApiProvider

DEPART = date.today() + timedelta(days=45)
REQUEST = SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)

PLACES = {
    "AMM": ("AMM", "95673320"),
    "SKP": ("SKP", "95673519"),
    "IST": ("IST", "95673681"),
}


def airport_response(query: str) -> dict:
    sky_id, entity_id = PLACES.get(query.upper(), (query.upper(), "0"))
    return {
        "status": True,
        "data": [
            {
                "skyId": sky_id,
                "entityId": entity_id,
                "presentation": {"title": query, "subtitle": "Country"},
                "navigation": {
                    "entityType": "AIRPORT",
                    "relevantFlightParams": {"skyId": sky_id, "entityId": entity_id},
                },
            }
        ],
    }


def segment(origin: str, destination: str, dep: str, arr: str, minutes: int, number: str) -> dict:
    return {
        "id": f"{origin}-{destination}",
        "origin": {"flightPlaceId": origin, "displayCode": origin, "name": origin},
        "destination": {"flightPlaceId": destination, "displayCode": destination, "name": destination},
        "departure": dep,
        "arrival": arr,
        "durationInMinutes": minutes,
        "flightNumber": number,
        "marketingCarrier": {"id": -32672, "name": "Turkish Airlines", "alternateId": "TK"},
        "operatingCarrier": {"id": -32672, "name": "Turkish Airlines", "alternateId": "TK"},
    }


CONNECTING_ITINERARY = {
    "id": "itin-connecting",
    "price": {"raw": 188.40, "formatted": "$189"},
    "isSelfTransfer": False,
    "isProtectedSelfTransfer": False,
    "legs": [
        {
            "id": "leg-1",
            "origin": {"displayCode": "AMM"},
            "destination": {"displayCode": "SKP"},
            "durationInMinutes": 415,
            "stopCount": 1,
            "carriers": {"marketing": [{"name": "Turkish Airlines", "alternateId": "TK"}]},
            "segments": [
                segment("AMM", "IST", "2026-09-01T09:00:00", "2026-09-01T11:20:00", 140, "813"),
                segment("IST", "SKP", "2026-09-01T14:35:00", "2026-09-01T15:55:00", 80, "1013"),
            ],
        }
    ],
}

SELF_TRANSFER_ITINERARY = {
    **CONNECTING_ITINERARY,
    "id": "itin-self-transfer",
    "price": {"raw": 99.00, "formatted": "$99"},
    "isSelfTransfer": True,
}


def build_provider(handler, tmp_path=None) -> RapidApiProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://air-scraper.p.rapidapi.com")
    cache = (tmp_path / "places.json") if tmp_path else None
    return RapidApiProvider(
        "test-key", "air-scraper.p.rapidapi.com", client=client, place_cache_path=cache
    )


def make_handler(itineraries: list[dict], status: str = "complete"):
    def handler(request: httpx.Request) -> httpx.Response:
        if "searchAirport" in request.url.path:
            return httpx.Response(200, json=airport_response(request.url.params["query"]))
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "context": {"status": status, "totalResults": len(itineraries)},
                    "itineraries": itineraries,
                },
            },
        )

    return handler


# ------------------------------------------------------------------ parsing


async def test_parses_a_connecting_itinerary(tmp_path) -> None:
    provider = build_provider(make_handler([CONNECTING_ITINERARY]), tmp_path)

    offers = await provider.search(REQUEST)

    assert len(offers) == 1
    offer = offers[0]
    assert offer.price_total == 188.40
    assert offer.outbound.path == ("AMM", "IST", "SKP")
    assert offer.primary_carrier == "TK"
    assert offer.outbound.segments[0].duration_minutes == 140
    # Ground time at the connection: 11:20 -> 14:35.
    assert offer.outbound.layover_minutes_after(0) == 195
    await provider.aclose()


async def test_intermediate_airport_is_named(tmp_path) -> None:
    """The one thing this app cannot work without."""
    provider = build_provider(make_handler([CONNECTING_ITINERARY]), tmp_path)

    offer = (await provider.search(REQUEST))[0]

    assert "IST" in offer.outbound.path[1:-1]
    await provider.aclose()


async def test_self_transfer_itineraries_are_excluded(tmp_path) -> None:
    """Separate tickets cannot carry a hidden-city fare.

    You collect bags and re-check in at the stop, and there is no single
    through-fare to undercut -- recommending one would be wrong, and it would
    look attractive because these are usually the cheapest results.
    """
    provider = build_provider(
        make_handler([SELF_TRANSFER_ITINERARY, CONNECTING_ITINERARY]), tmp_path
    )

    offers = await provider.search(REQUEST)

    assert [offer.offer_id for offer in offers] == ["itin-connecting"]
    assert all(offer.price_total != 99.00 for offer in offers)
    await provider.aclose()


async def test_protected_self_transfer_is_also_excluded(tmp_path) -> None:
    itinerary = {**CONNECTING_ITINERARY, "isSelfTransfer": False, "isProtectedSelfTransfer": True}
    provider = build_provider(make_handler([itinerary]), tmp_path)

    assert await provider.search(REQUEST) == []
    await provider.aclose()


async def test_partial_results_are_still_used(tmp_path) -> None:
    """Skyscanner-style searches stream; polling would just spend quota."""
    provider = build_provider(make_handler([CONNECTING_ITINERARY], status="incomplete"), tmp_path)

    assert len(await provider.search(REQUEST)) == 1
    await provider.aclose()


async def test_unparseable_itineraries_are_skipped(tmp_path) -> None:
    provider = build_provider(make_handler([{"id": "broken"}, CONNECTING_ITINERARY]), tmp_path)

    assert len(await provider.search(REQUEST)) == 1
    await provider.aclose()


# ------------------------------------------------------------- place caching


async def test_airport_ids_are_resolved_once_and_cached(tmp_path) -> None:
    """On a metered plan, re-resolving airports on every search is real money."""
    lookups: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "searchAirport" in request.url.path:
            lookups.append(request.url.params["query"])
            return httpx.Response(200, json=airport_response(request.url.params["query"]))
        return httpx.Response(
            200, json={"status": True, "data": {"itineraries": [CONNECTING_ITINERARY]}}
        )

    provider = build_provider(handler, tmp_path)
    await provider.search(REQUEST)
    await provider.search(REQUEST)
    await provider.search(REQUEST)

    # Two airports, resolved once each, despite three searches.
    assert sorted(lookups) == ["AMM", "SKP"]
    await provider.aclose()


async def test_place_cache_survives_a_restart(tmp_path) -> None:
    handler = make_handler([CONNECTING_ITINERARY])
    first = build_provider(handler, tmp_path)
    await first.search(REQUEST)
    await first.aclose()

    cache_file = tmp_path / "places.json"
    assert cache_file.is_file()
    assert set(json.loads(cache_file.read_text())) == {"AMM", "SKP"}

    lookups: list[str] = []

    def counting_handler(request: httpx.Request) -> httpx.Response:
        if "searchAirport" in request.url.path:
            lookups.append(request.url.params["query"])
        return handler(request)

    second = build_provider(counting_handler, tmp_path)
    await second.search(REQUEST)

    assert lookups == []  # loaded from disk, no quota spent
    await second.aclose()


async def test_unresolvable_airport_returns_empty(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "searchAirport" in request.url.path:
            return httpx.Response(200, json={"status": True, "data": []})
        return httpx.Response(200, json={"status": True, "data": {"itineraries": []}})

    provider = build_provider(handler, tmp_path)

    assert await provider.search(REQUEST) == []
    await provider.aclose()


# ------------------------------------------------------------ failure handling


async def test_bad_key_raises_a_clear_error(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Invalid API key"})

    provider = build_provider(handler, tmp_path)

    with pytest.raises(ProviderError, match="RAPIDAPI_KEY"):
        await provider.search(REQUEST)
    await provider.aclose()


async def test_exhausted_monthly_quota_fails_fast(tmp_path) -> None:
    """RapidAPI returns 429 for both throttling and a spent quota. Retrying a
    spent quota cannot succeed -- it just burns time before failing anyway."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            429,
            headers={"x-ratelimit-requests-remaining": "0"},
            json={"message": "Too many requests"},
        )

    provider = build_provider(handler, tmp_path)

    with pytest.raises(ProviderError, match="quota is exhausted"):
        await provider.search(REQUEST)
    assert attempts == 1, "must not retry an exhausted quota"
    await provider.aclose()


async def test_throttling_with_quota_left_is_retried(tmp_path) -> None:
    """A genuine rate limit is temporary and should be waited out."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"x-ratelimit-requests-remaining": "480", "retry-after": "1"},
                json={"message": "Too many requests"},
            )
        if "searchAirport" in request.url.path:
            return httpx.Response(200, json=airport_response(request.url.params["query"]))
        return httpx.Response(200, json={"status": True, "data": {"itineraries": []}})

    provider = build_provider(handler, tmp_path)
    await provider.search(REQUEST)

    assert attempts > 1, "a temporary throttle should be retried"
    await provider.aclose()


async def test_quota_remaining_is_tracked(tmp_path) -> None:
    base = make_handler([CONNECTING_ITINERARY])

    def handler(request: httpx.Request) -> httpx.Response:
        response = base(request)
        response.headers["x-ratelimit-requests-remaining"] = "37"
        return response

    provider = build_provider(handler, tmp_path)
    await provider.search(REQUEST)

    assert provider.quota_remaining == "37"
    await provider.aclose()


async def test_not_subscribed_names_both_likely_causes(tmp_path) -> None:
    """403 means either 'not subscribed' or 'quota spent', and the operator
    needs to know which to check."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "You are not subscribed"})

    provider = build_provider(handler, tmp_path)

    with pytest.raises(ProviderError, match="quota"):
        await provider.search(REQUEST)
    await provider.aclose()


def test_missing_credentials_are_rejected_at_construction() -> None:
    with pytest.raises(ProviderError, match="credentials missing"):
        RapidApiProvider(api_key=None, host=None)
    with pytest.raises(ProviderError, match="credentials missing"):
        RapidApiProvider(api_key="key", host=None)


# ----------------------------------------------------------------- end to end


async def test_analyzer_finds_a_hidden_city_in_rapidapi_data(tmp_path) -> None:
    from app.core.analyzer import analyse

    provider = build_provider(make_handler([CONNECTING_ITINERARY]), tmp_path)
    extended = await provider.search(REQUEST)

    direct = {
        "id": "itin-direct",
        "price": {"raw": 260.00, "formatted": "$260"},
        "isSelfTransfer": False,
        "legs": [
            {
                "id": "leg-direct",
                "durationInMinutes": 140,
                "stopCount": 0,
                "carriers": {"marketing": [{"name": "Turkish Airlines", "alternateId": "TK"}]},
                "segments": [
                    segment("AMM", "IST", "2026-09-01T09:00:00", "2026-09-01T11:20:00", 140, "813")
                ],
            }
        ],
    }
    baseline_provider = build_provider(make_handler([direct]), tmp_path)
    baseline = await baseline_provider.search(
        SearchRequest(origin="AMM", destination="IST", departure_date=DEPART)
    )

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert result.baseline_price == 260.0
    assert len(result.hidden_options) == 1
    option = result.hidden_options[0]
    assert option.deplane_iata == "IST"
    assert option.ticketed_iata == "SKP"
    assert option.savings == pytest.approx(71.6)
    assert option.booking("en")["url"] == "https://www.turkishairlines.com"

    await provider.aclose()
    await baseline_provider.aclose()
