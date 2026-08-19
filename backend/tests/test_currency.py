"""Pricing a trip in a currency other than USD.

The bug these cover: the offer cache was keyed on route, date, cabin and
passenger count, but *not* on currency, which it stored as a property of the
row instead. Searching AMM->LIS in EUR and then in USD returned the euro
offers under a dollar label, so one page showed two currencies at once.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.providers.base import Offer, SearchRequest


def request_in(currency: str) -> SearchRequest:
    return SearchRequest(
        origin="AMM",
        destination="LIS",
        departure_date=date(2026, 11, 5),
        currency=currency,
    )


def test_cache_key_separates_currencies() -> None:
    assert request_in("EUR").cache_key("mock") != request_in("USD").cache_key("mock")


def test_cache_key_is_otherwise_stable() -> None:
    """Two identical requests must still share a cache entry."""
    assert request_in("EUR").cache_key("mock") == request_in("EUR").cache_key("mock")


@pytest.mark.asyncio
async def test_a_second_currency_is_not_served_from_the_first(session) -> None:
    from app.providers.mock import MockFlightProvider
    from app.services.cache import OfferCacheRepository

    provider = MockFlightProvider()
    cache = OfferCacheRepository(session, provider.name)

    eur_request = request_in("EUR")
    eur_offers = await provider.search(eur_request)
    await cache.put(eur_request, eur_offers)
    await session.commit()

    # Same route, same date, same cabin -- different currency.
    assert await cache.get(request_in("USD")) is None
    # And the original is still there.
    cached = await cache.get(eur_request)
    assert cached is not None
    assert {offer.currency for offer in cached} == {"EUR"}


@pytest.mark.asyncio
async def test_one_response_never_mixes_currencies(client) -> None:
    """The end-to-end symptom, in the order that produced it."""
    seen: dict[str, set[str]] = {}
    for currency in ("EUR", "USD", "JOD"):
        response = await client.post(
            "/api/search?wait=true",
            json={
                "origin": "AMM",
                "destination": "LIS",
                "departure_date": "2026-11-05",
                "trip_type": "one_way",
                "lang": "en",
                "currency": currency,
            },
        )
        assert response.status_code == 200
        seen[currency] = _currencies_in(response.json())

    for requested, found in seen.items():
        assert found == {requested}, f"asked for {requested}, response carried {found}"


def _currencies_in(node: object) -> set[str]:
    """Every ``currency`` value anywhere in a nested payload."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "currency" and isinstance(value, str):
                found.add(value)
            else:
                found |= _currencies_in(value)
    elif isinstance(node, list):
        for item in node:
            found |= _currencies_in(item)
    return found


@pytest.mark.asyncio
async def test_offers_carry_the_requested_currency() -> None:
    from app.providers.mock import MockFlightProvider

    offers: list[Offer] = await MockFlightProvider().search(request_in("JOD"))
    assert offers
    assert all(offer.currency == "JOD" for offer in offers)
