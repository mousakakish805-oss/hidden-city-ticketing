"""SerpApi Google Flights provider.

The payloads here follow SerpApi's documented shape, including the two traits
that make it unlike the other providers: naive local time strings with no
offset, and the carrier code living inside ``flight_number`` rather than in a
field of its own.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.providers.base import ProviderError, SearchRequest
from app.providers.serpapi import SerpApiProvider

REQUEST = SearchRequest(origin="AMM", destination="SCQ", departure_date=date(2026, 9, 15))

# AMM -> MAD -> SCQ. The connection at Madrid is what hidden-city detection is
# entirely about, so the layover and both leg endpoints must survive parsing.
TWO_LEG_RESPONSE = {
    "best_flights": [
        {
            "flights": [
                {
                    "departure_airport": {
                        "name": "Queen Alia",
                        "id": "AMM",
                        "time": "2026-09-15 13:45",
                    },
                    "arrival_airport": {"name": "Barajas", "id": "MAD", "time": "2026-09-15 19:12"},
                    "duration": 387,
                    "airplane": "Airbus A320",
                    "airline": "Iberia",
                    "flight_number": "IB 495",
                    "travel_class": "Economy",
                },
                {
                    "departure_airport": {
                        "name": "Barajas",
                        "id": "MAD",
                        "time": "2026-09-15 20:47",
                    },
                    "arrival_airport": {
                        "name": "Santiago",
                        "id": "SCQ",
                        "time": "2026-09-15 21:58",
                    },
                    "duration": 71,
                    "airplane": "Airbus A319",
                    "airline": "Iberia",
                    "flight_number": "IB 1684",
                    "travel_class": "Economy",
                },
            ],
            "layovers": [{"duration": 95, "name": "Barajas", "id": "MAD"}],
            "total_duration": 553,
            "price": 159,
            "type": "One way",
            "booking_token": "tok_abc123",
        }
    ],
    "other_flights": [
        {
            "flights": [
                {
                    "departure_airport": {
                        "name": "Queen Alia",
                        "id": "AMM",
                        "time": "2026-09-15 04:35",
                    },
                    "arrival_airport": {
                        "name": "Santiago",
                        "id": "SCQ",
                        "time": "2026-09-15 14:20",
                    },
                    "duration": 405,
                    "airline": "Royal Jordanian",
                    "flight_number": "RJ 111",
                    "travel_class": "Economy",
                }
            ],
            "layovers": [],
            "total_duration": 405,
            "price": 240,
            "type": "One way",
        }
    ],
}


def provider_returning(payload: object, status: int = 200) -> SerpApiProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/account":
            return httpx.Response(200, json={"total_searches_left": 231})
        return httpx.Response(status, json=payload)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://serpapi.com"
    )
    return SerpApiProvider(api_key="test-key", client=client)


@pytest.mark.asyncio
async def test_parses_both_result_groups_cheapest_first() -> None:
    provider = provider_returning(TWO_LEG_RESPONSE)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    # best_flights and other_flights both count: a hidden-city itinerary is an
    # awkward one Google has no reason to promote.
    assert [offer.price_total for offer in offers] == [159.0, 240.0]


@pytest.mark.asyncio
async def test_names_the_connecting_airport() -> None:
    """Without this the whole technique is undetectable."""
    provider = provider_returning(TWO_LEG_RESPONSE)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    itinerary = offers[0].outbound
    assert itinerary.path == ("AMM", "MAD", "SCQ")
    assert itinerary.stop_count == 1


@pytest.mark.asyncio
async def test_layover_is_computed_from_local_times_at_one_airport() -> None:
    """Naive timestamps are safe here: both sides are in Madrid's timezone."""
    provider = provider_returning(TWO_LEG_RESPONSE)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    # 19:12 arrival -> 20:47 departure, and SerpApi agrees it is 95 minutes.
    assert offers[0].outbound.layover_minutes_after(0) == 95


@pytest.mark.asyncio
async def test_carrier_code_is_split_out_of_the_flight_number() -> None:
    """`airline` is a display name; only `flight_number` carries the code."""
    provider = provider_returning(TWO_LEG_RESPONSE)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    first = offers[0].outbound.segments[0]
    assert (first.carrier, first.flight_number) == ("IB", "495")
    assert offers[0].primary_carrier == "IB"


@pytest.mark.asyncio
async def test_journey_length_comes_from_the_api_not_the_timestamps() -> None:
    """Local times cross timezones, so arithmetic on them would be wrong."""
    provider = provider_returning(TWO_LEG_RESPONSE)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    assert offers[0].outbound.duration_minutes == 553


@pytest.mark.asyncio
async def test_every_offer_is_one_way() -> None:
    """A hidden-city ticket cannot survive a return leg; type=2 is enforced."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/account":
            return httpx.Response(200, json={"total_searches_left": 231})
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=TWO_LEG_RESPONSE)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://serpapi.com"
    )
    provider = SerpApiProvider(api_key="test-key", client=client)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    assert captured["type"] == "2"
    assert "return_date" not in captured
    assert all(offer.is_one_way for offer in offers)


@pytest.mark.asyncio
async def test_asks_for_the_cheapest_not_the_most_convenient() -> None:
    """The baseline is the number every saving is measured against.

    Google's default "Best" ranking drops cheaper itineraries: AMM->DME came
    back at JOD 366 under it while the real cheapest was JOD 241, which would
    have turned fares more expensive than the cheapest ticket into reported
    savings.
    """
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/account":
            return httpx.Response(200, json={"total_searches_left": 231})
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=TWO_LEG_RESPONSE)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://serpapi.com"
    )
    provider = SerpApiProvider(api_key="test-key", client=client)
    await provider.search(REQUEST)
    await provider.aclose()

    assert captured["sort_by"] == "2"


@pytest.mark.asyncio
async def test_a_market_with_no_flights_is_empty_not_fatal() -> None:
    """Thin routes are ordinary; the batch engine must keep going."""
    provider = provider_returning(
        {"error": "Google Flights hasn't returned any results for this query."}
    )
    offers = await provider.search(REQUEST)
    await provider.aclose()

    assert offers == []


@pytest.mark.asyncio
async def test_a_rejected_key_is_fatal() -> None:
    provider = provider_returning({"error": "Invalid API key"}, status=401)
    with pytest.raises(ProviderError, match="api key"):
        await provider.search(REQUEST)
    await provider.aclose()


@pytest.mark.asyncio
async def test_a_spent_plan_says_so_instead_of_retrying() -> None:
    """429 covers both throttling and an exhausted plan; only one is retryable."""
    provider = provider_returning(
        {"error": "You've ran out of searches for this month."}, status=429
    )
    with pytest.raises(ProviderError, match="exhausted"):
        await provider.search(REQUEST)
    assert provider.quota_remaining == 0
    await provider.aclose()


@pytest.mark.asyncio
async def test_an_unpriced_offer_is_skipped_without_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Observed on the very first live search against AMM -> IST.

    Google returns itineraries it will not quote a price for. There is nothing
    wrong with the payload and nothing this tool can do with the flight, so it
    goes quietly -- warning about it would fire on essentially every search and
    train the reader to ignore the log.
    """
    payload = {
        "best_flights": [
            {"flights": TWO_LEG_RESPONSE["best_flights"][0]["flights"]},  # no price
            TWO_LEG_RESPONSE["best_flights"][0],
        ]
    }
    provider = provider_returning(payload)
    with caplog.at_level("WARNING"):
        offers = await provider.search(REQUEST)
    await provider.aclose()

    assert [offer.price_total for offer in offers] == [159.0]
    assert caplog.records == []


@pytest.mark.asyncio
async def test_a_malformed_offer_still_warns(caplog: pytest.LogCaptureFixture) -> None:
    """A price that is not a number is a real problem, and must be visible."""
    payload = {
        "best_flights": [
            {"flights": TWO_LEG_RESPONSE["best_flights"][0]["flights"], "price": "free"}
        ]
    }
    provider = provider_returning(payload)
    with caplog.at_level("WARNING"):
        offers = await provider.search(REQUEST)
    await provider.aclose()

    assert offers == []
    assert any("malformed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_unparseable_offers_are_skipped_not_fatal() -> None:
    payload = {
        "best_flights": [
            {"flights": [], "price": 100},
            TWO_LEG_RESPONSE["best_flights"][0],
        ]
    }
    provider = provider_returning(payload)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    assert len(offers) == 1
    assert offers[0].price_total == 159.0


@pytest.mark.asyncio
async def test_reports_the_remaining_balance_for_the_health_badge() -> None:
    provider = provider_returning(TWO_LEG_RESPONSE)
    await provider.search(REQUEST)
    await provider.aclose()

    assert provider.quota_remaining == 231


@pytest.mark.asyncio
async def test_a_failed_balance_check_does_not_fail_the_search() -> None:
    """Not knowing the quota must never lose a result we already have."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/account":
            return httpx.Response(500, text="nope")
        return httpx.Response(200, json=TWO_LEG_RESPONSE)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://serpapi.com"
    )
    provider = SerpApiProvider(api_key="test-key", client=client)
    offers = await provider.search(REQUEST)
    await provider.aclose()

    assert len(offers) == 2
    assert provider.quota_remaining is None


def test_requires_a_key() -> None:
    with pytest.raises(ProviderError, match="SERPAPI_KEY"):
        SerpApiProvider(api_key="")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("IB 495", ("IB", "495")),
        ("U2 8021", ("U2", "8021")),  # easyJet: digit inside the code
        ("9W 12", ("9W", "12")),
        ("BA301", ("BA", "301")),  # no space
        (None, ("", "")),
    ],
)
def test_flight_number_splitting(raw: str | None, expected: tuple[str, str]) -> None:
    assert SerpApiProvider._split_flight_number(raw) == expected
