"""Provider normalisation: mock determinism and Amadeus payload parsing."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from app.providers.amadeus import AmadeusProvider
from app.providers.base import ProviderError, SearchRequest, format_minutes, parse_iso_duration
from app.providers.mock import MockFlightProvider

DEPART = date.today() + timedelta(days=45)


# ------------------------------------------------------------------ utilities


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PT2H20M", 140),
        ("PT45M", 45),
        ("PT3H", 180),
        ("P1DT2H30M", 1590),
        ("PT1H30M45S", 90),
        ("", 0),
        (None, 0),
        ("nonsense", 0),
    ],
)
def test_parse_iso_duration(value: str | None, expected: int) -> None:
    assert parse_iso_duration(value) == expected


@pytest.mark.parametrize(
    ("minutes", "expected"), [(265, "4h 25m"), (60, "1h 00m"), (45, "45m"), (0, "0m")]
)
def test_format_minutes(minutes: int, expected: str) -> None:
    assert format_minutes(minutes) == expected


# ----------------------------------------------------------------- mock provider


async def test_mock_results_are_deterministic() -> None:
    request = SearchRequest(origin="AMM", destination="IST", departure_date=DEPART)

    first = await MockFlightProvider().search(request)
    second = await MockFlightProvider().search(request)

    assert [offer.price_total for offer in first] == [offer.price_total for offer in second]
    assert [offer.outbound.path for offer in first] == [offer.outbound.path for offer in second]


async def test_mock_offers_are_sorted_by_price_and_well_formed() -> None:
    offers = await MockFlightProvider().search(
        SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)
    )

    assert offers
    prices = [offer.price_total for offer in offers]
    assert prices == sorted(prices)
    for offer in offers:
        assert offer.is_one_way
        assert offer.outbound.path[0] == "AMM"
        assert offer.outbound.path[-1] == "SKP"
        assert offer.price_total > 0
        for segment in offer.outbound.segments:
            assert segment.arrival_at > segment.departure_at


async def test_mock_reproduces_the_fortress_hub_anomaly() -> None:
    """The premise of the whole app: AMM->SKP via IST undercuts AMM->IST."""
    provider = MockFlightProvider()

    to_hub = await provider.search(
        SearchRequest(origin="AMM", destination="IST", departure_date=DEPART)
    )
    beyond_hub = await provider.search(
        SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)
    )

    via_ist = [
        offer for offer in beyond_hub if "IST" in offer.outbound.path[1:-1]
    ]
    assert via_ist, "expected at least one AMM->SKP itinerary connecting in IST"
    assert min(offer.price_total for offer in via_ist) < min(
        offer.price_total for offer in to_hub
    )


@pytest.mark.parametrize(
    ("origin", "destination"),
    [("AMM", "IST"), ("JFK", "LHR"), ("DXB", "BOM"), ("GRU", "LIS"), ("NBO", "AMS")],
)
async def test_mock_only_invents_routes_that_are_actually_flown(
    origin: str, destination: str
) -> None:
    """Synthetic data must still be *plausible* data.

    Every leg has to be a real city pair, operated by an airline that really
    flies it -- otherwise the demo undermines confidence in correct output.
    """
    from app.data.routes import route_operators

    offers = await MockFlightProvider().search(
        SearchRequest(origin=origin, destination=destination, departure_date=DEPART)
    )
    assert offers

    for offer in offers:
        for segment in offer.outbound.segments:
            operators = route_operators(segment.origin, segment.destination)
            assert operators, f"{segment.origin}->{segment.destination} is not a served route"
            assert segment.carrier in operators, (
                f"{segment.carrier} does not fly {segment.origin}->{segment.destination}"
            )


async def test_mock_connections_are_sold_by_a_single_carrier() -> None:
    """A hidden-city fare has to be one ticket, so one operating carrier."""
    offers = await MockFlightProvider().search(
        SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)
    )

    for offer in offers:
        carriers = {segment.carrier for segment in offer.outbound.segments}
        assert len(carriers) == 1


async def test_mock_returns_nothing_for_unknown_or_identical_airports() -> None:
    provider = MockFlightProvider()

    assert await provider.search(
        SearchRequest(origin="AMM", destination="ZZZ", departure_date=DEPART)
    ) == []
    assert await provider.search(
        SearchRequest(origin="AMM", destination="AMM", departure_date=DEPART)
    ) == []


async def test_mock_prices_scale_with_party_size() -> None:
    one = await MockFlightProvider().search(
        SearchRequest(origin="AMM", destination="IST", departure_date=DEPART, adults=1)
    )
    two = await MockFlightProvider().search(
        SearchRequest(origin="AMM", destination="IST", departure_date=DEPART, adults=2)
    )

    assert min(o.price_total for o in two) > min(o.price_total for o in one)


# --------------------------------------------------------------- amadeus parsing


AMADEUS_OFFER = {
    "type": "flight-offer",
    "id": "1",
    "numberOfBookableSeats": 4,
    "itineraries": [
        {
            "duration": "PT7H55M",
            "segments": [
                {
                    "departure": {"iataCode": "AMM", "terminal": "1", "at": "2026-09-01T09:00:00"},
                    "arrival": {"iataCode": "IST", "at": "2026-09-01T11:20:00"},
                    "carrierCode": "TK",
                    "number": "813",
                    "aircraft": {"code": "32N"},
                    "operating": {"carrierCode": "TK"},
                    "duration": "PT2H20M",
                    "id": "1",
                    "numberOfStops": 0,
                },
                {
                    "departure": {"iataCode": "IST", "at": "2026-09-01T14:35:00"},
                    "arrival": {"iataCode": "SKP", "at": "2026-09-01T15:55:00"},
                    "carrierCode": "TK",
                    "number": "1013",
                    "aircraft": {"code": "738"},
                    "duration": "PT1H20M",
                    "id": "2",
                    "numberOfStops": 0,
                },
            ],
        }
    ],
    "price": {"currency": "USD", "total": "188.40", "grandTotal": "191.90"},
    "validatingAirlineCodes": ["TK"],
    "travelerPricings": [
        {
            "fareDetailsBySegment": [
                {"segmentId": "1", "cabin": "ECONOMY", "includedCheckedBags": {"quantity": 1}},
                {"segmentId": "2", "cabin": "ECONOMY", "includedCheckedBags": {"quantity": 1}},
            ]
        }
    ],
}


def build_amadeus_provider(handler) -> AmadeusProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://test.api.amadeus.com")
    return AmadeusProvider("id", "secret", client=client)


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/token"):
        return httpx.Response(200, json={"access_token": "tok", "expires_in": 1799})
    return httpx.Response(200, json={"data": [AMADEUS_OFFER], "dictionaries": {}})


async def test_amadeus_parses_a_multi_segment_offer() -> None:
    provider = build_amadeus_provider(default_handler)

    offers = await provider.search(
        SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)
    )

    assert len(offers) == 1
    offer = offers[0]
    # grandTotal wins over total: it is what the traveller actually pays.
    assert offer.price_total == 191.90
    assert offer.outbound.path == ("AMM", "IST", "SKP")
    assert offer.outbound.stop_count == 1
    assert offer.primary_carrier == "TK"
    assert offer.bookable_seats == 4
    assert offer.outbound.segments[0].duration_minutes == 140
    # Ground time at the connection: 11:20 -> 14:35.
    assert offer.outbound.layover_minutes_after(0) == 195
    await provider.aclose()


async def test_amadeus_reuses_its_token_across_searches() -> None:
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path.endswith("/token"):
            token_calls += 1
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 1799})
        return httpx.Response(200, json={"data": [AMADEUS_OFFER]})

    provider = build_amadeus_provider(handler)
    request = SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)
    await provider.search(request)
    await provider.search(request)

    assert token_calls == 1
    await provider.aclose()


async def test_amadeus_treats_a_rejected_market_as_empty_not_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 1799})
        return httpx.Response(400, json={"errors": [{"detail": "no route"}]})

    provider = build_amadeus_provider(handler)

    assert await provider.search(
        SearchRequest(origin="AMM", destination="ZZZ", departure_date=DEPART)
    ) == []
    await provider.aclose()


async def test_amadeus_skips_unparseable_offers_but_keeps_the_rest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 1799})
        return httpx.Response(
            200, json={"data": [{"id": "broken"}, AMADEUS_OFFER]}
        )

    provider = build_amadeus_provider(handler)

    offers = await provider.search(
        SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)
    )

    assert len(offers) == 1
    await provider.aclose()


async def test_amadeus_raises_when_authentication_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    provider = build_amadeus_provider(handler)

    with pytest.raises(ProviderError, match="authentication failed"):
        await provider.search(
            SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)
        )
    await provider.aclose()


def test_amadeus_requires_credentials() -> None:
    with pytest.raises(ProviderError, match="credentials missing"):
        AmadeusProvider(client_id=None, client_secret=None)
