"""Duffel provider: two-step search, payload parsing and failure handling."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from app.providers.base import ProviderError, SearchRequest
from app.providers.duffel import DuffelProvider

DEPART = date.today() + timedelta(days=45)
REQUEST = SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)

OFFER_REQUEST_RESPONSE = {"data": {"id": "orq_0000ABC", "slices": [], "passengers": []}}

# A connecting itinerary: the shape hidden-city detection depends on.
DUFFEL_OFFER = {
    "id": "off_0000XYZ",
    "total_amount": "188.40",
    "total_currency": "USD",
    "base_amount": "150.00",
    "owner": {"iata_code": "TK", "name": "Turkish Airlines"},
    "slices": [
        {
            "duration": "PT6H55M",
            "origin": {"iata_code": "AMM"},
            "destination": {"iata_code": "SKP"},
            "segments": [
                {
                    "id": "seg_1",
                    "origin": {"iata_code": "AMM"},
                    "destination": {"iata_code": "IST"},
                    "departing_at": "2026-09-01T09:00:00",
                    "arriving_at": "2026-09-01T11:20:00",
                    "duration": "PT2H20M",
                    "marketing_carrier": {"iata_code": "TK", "name": "Turkish Airlines"},
                    "operating_carrier": {"iata_code": "TK"},
                    "marketing_carrier_flight_number": "813",
                    "aircraft": {"iata_code": "32N"},
                    "passengers": [{"cabin_class": "economy", "baggages": []}],
                },
                {
                    "id": "seg_2",
                    "origin": {"iata_code": "IST"},
                    "destination": {"iata_code": "SKP"},
                    "departing_at": "2026-09-01T14:35:00",
                    "arriving_at": "2026-09-01T15:55:00",
                    "duration": "PT1H20M",
                    "marketing_carrier": {"iata_code": "TK", "name": "Turkish Airlines"},
                    "operating_carrier": {"iata_code": "TK"},
                    "marketing_carrier_flight_number": "1013",
                    "aircraft": {"iata_code": "738"},
                    "passengers": [{"cabin_class": "economy", "baggages": []}],
                },
            ],
        }
    ],
}


def build_provider(handler, token: str = "duffel_test_abc123") -> DuffelProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://api.duffel.com")
    return DuffelProvider(token, client=client)


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/air/offer_requests":
        return httpx.Response(201, json=OFFER_REQUEST_RESPONSE)
    return httpx.Response(200, json={"data": [DUFFEL_OFFER]})


# ------------------------------------------------------------------ parsing


async def test_parses_a_connecting_offer() -> None:
    provider = build_provider(default_handler)

    offers = await provider.search(REQUEST)

    assert len(offers) == 1
    offer = offers[0]
    assert offer.price_total == 188.40
    assert offer.currency == "USD"
    assert offer.outbound.path == ("AMM", "IST", "SKP")
    assert offer.outbound.stop_count == 1
    assert offer.primary_carrier == "TK"
    assert offer.primary_carrier_name == "Turkish Airlines"
    assert offer.outbound.segments[0].duration_minutes == 140
    # Ground time at the connection: 11:20 -> 14:35.
    assert offer.outbound.layover_minutes_after(0) == 195
    await provider.aclose()


async def test_offer_exposes_the_intermediate_airport() -> None:
    """Without a named intermediate stop, hidden-city detection is impossible."""
    provider = build_provider(default_handler)

    offer = (await provider.search(REQUEST))[0]

    assert "IST" in offer.outbound.path[1:-1]
    await provider.aclose()


async def test_reports_no_baggage_information() -> None:
    """Duffel sends baggage beside the cabin; we deliberately ignore it."""
    provider = build_provider(default_handler)

    payload = (await provider.search(REQUEST))[0].to_dict()

    assert "included_checked_bags" not in payload
    await provider.aclose()


# --------------------------------------------------------------- request shape


async def test_search_is_two_steps_and_bounds_the_payload() -> None:
    """Offers are fetched separately so a busy market cannot flood the fan-out."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/air/offer_requests":
            return httpx.Response(201, json=OFFER_REQUEST_RESPONSE)
        return httpx.Response(200, json={"data": [DUFFEL_OFFER]})

    provider = build_provider(handler)
    await provider.search(REQUEST)

    create, fetch = seen
    assert create.method == "POST"
    assert create.url.params["return_offers"] == "false"
    assert fetch.method == "GET"
    assert fetch.url.params["offer_request_id"] == "orq_0000ABC"
    assert fetch.url.params["sort"] == "total_amount"
    assert int(fetch.url.params["limit"]) <= 200
    await provider.aclose()


async def test_every_request_carries_auth_and_version_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/air/offer_requests":
            return httpx.Response(201, json=OFFER_REQUEST_RESPONSE)
        return httpx.Response(200, json={"data": []})

    provider = build_provider(handler)
    await provider.search(REQUEST)

    for request in seen:
        assert request.headers["authorization"] == "Bearer duffel_test_abc123"
        # Duffel changes behaviour without an explicit version.
        assert request.headers["duffel-version"] == "v2"
    await provider.aclose()


async def test_connections_are_requested_so_hidden_cities_can_exist() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/air/offer_requests":
            import json as jsonlib

            captured.update(jsonlib.loads(request.content)["data"])
            return httpx.Response(201, json=OFFER_REQUEST_RESPONSE)
        return httpx.Response(200, json={"data": []})

    provider = build_provider(handler)
    await provider.search(
        SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART, adults=2)
    )

    assert captured["max_connections"] >= 1
    assert captured["cabin_class"] == "economy"
    assert len(captured["passengers"]) == 2
    assert captured["slices"][0]["origin"] == "AMM"
    await provider.aclose()


# ------------------------------------------------------------ failure handling


async def test_unserved_market_returns_empty_not_an_error() -> None:
    """A market Duffel will not quote must not abort the whole batch run."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422, json={"errors": [{"title": "Invalid route", "message": "no route"}]}
        )

    provider = build_provider(handler)

    assert await provider.search(REQUEST) == []
    await provider.aclose()


async def test_bad_token_raises_a_clear_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"title": "Unauthorized"}]})

    provider = build_provider(handler)

    with pytest.raises(ProviderError, match="access token"):
        await provider.search(REQUEST)
    await provider.aclose()


async def test_unparseable_offers_are_skipped_not_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/air/offer_requests":
            return httpx.Response(201, json=OFFER_REQUEST_RESPONSE)
        return httpx.Response(200, json={"data": [{"id": "broken"}, DUFFEL_OFFER]})

    provider = build_provider(handler)

    assert len(await provider.search(REQUEST)) == 1
    await provider.aclose()


async def test_server_errors_are_retried_then_raised() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"errors": [{"title": "unavailable"}]})

    provider = build_provider(handler)

    with pytest.raises(ProviderError):
        await provider.search(REQUEST)
    assert attempts > 1
    await provider.aclose()


def test_missing_token_is_rejected_at_construction() -> None:
    with pytest.raises(ProviderError, match="token missing"):
        DuffelProvider(access_token=None)


# ------------------------------------------------------------------- mode


@pytest.mark.parametrize(
    ("token", "live"),
    [("duffel_live_abc", True), ("duffel_test_abc", False)],
)
def test_live_mode_is_detected_from_the_token(token: str, live: bool) -> None:
    """A test token returns sandbox inventory, which users must be warned about."""
    provider = build_provider(default_handler, token=token)

    assert provider.is_live_mode is live


# The synthetic carrier Duffel injects into every sandbox market, always
# undercutting the real fares beside it.
DUFFEL_AIRWAYS_OFFER = {
    **DUFFEL_OFFER,
    "id": "off_test_airline",
    "total_amount": "42.00",
    "owner": {"iata_code": "ZZ", "name": "Duffel Airways"},
    "slices": [
        {
            "duration": "PT2H20M",
            "origin": {"iata_code": "AMM"},
            "destination": {"iata_code": "SKP"},
            "segments": [
                {
                    **DUFFEL_OFFER["slices"][0]["segments"][0],
                    "destination": {"iata_code": "SKP"},
                    "marketing_carrier": {"iata_code": "ZZ", "name": "Duffel Airways"},
                }
            ],
        }
    ],
}


def mixed_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/air/offer_requests":
        return httpx.Response(201, json=OFFER_REQUEST_RESPONSE)
    return httpx.Response(200, json={"data": [DUFFEL_AIRWAYS_OFFER, DUFFEL_OFFER]})


async def test_sandbox_airline_is_dropped_from_test_results() -> None:
    """Left in, its fake cheap nonstop becomes the baseline for every search
    and hides every genuine fare -- fatal for a price-comparison tool."""
    provider = build_provider(mixed_handler, token="duffel_test_abc")

    offers = await provider.search(REQUEST)

    assert [offer.primary_carrier for offer in offers] == ["TK"]
    assert all(offer.price_total != 42.00 for offer in offers)
    await provider.aclose()


async def test_live_results_are_never_filtered() -> None:
    """Live inventory has no ZZ, and silently dropping a real carrier would
    be a serious correctness bug."""
    provider = build_provider(mixed_handler, token="duffel_live_abc")

    offers = await provider.search(REQUEST)

    assert len(offers) == 2
    await provider.aclose()


# ----------------------------------------------------------------- end to end


async def test_analyzer_finds_a_hidden_city_in_duffel_data() -> None:
    """The whole point: a Duffel connecting offer must drive the detector."""
    from app.core.analyzer import analyse

    provider = build_provider(default_handler)
    extended = await provider.search(REQUEST)

    baseline_offer = {
        **DUFFEL_OFFER,
        "id": "off_direct",
        "total_amount": "260.00",
        "slices": [
            {
                "duration": "PT2H20M",
                "origin": {"iata_code": "AMM"},
                "destination": {"iata_code": "IST"},
                "segments": [DUFFEL_OFFER["slices"][0]["segments"][0]],
            }
        ],
    }

    def baseline_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/air/offer_requests":
            return httpx.Response(201, json=OFFER_REQUEST_RESPONSE)
        return httpx.Response(200, json={"data": [baseline_offer]})

    baseline_provider = build_provider(baseline_handler)
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
    booking = option.booking("en")
    assert booking["carrier_name"] == "Turkish Airlines"
    assert booking["url"] == "https://www.turkishairlines.com"
    assert "SKP" in booking["instructions"]

    await provider.aclose()
    await baseline_provider.aclose()
