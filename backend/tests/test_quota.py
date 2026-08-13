"""Quota visibility.

On a metered plan the single worst failure mode is discovering the allowance
is gone through a broken search. The provider tracks what the API reports and
health surfaces it, so an operator can see the balance first.
"""

from __future__ import annotations

import httpx
from httpx import AsyncClient

from app.providers.rapidapi import RapidApiProvider
from app.providers.registry import set_provider
from tests.test_rapidapi import CONNECTING_ITINERARY, REQUEST, make_handler


def build(remaining: str | None, tmp_path) -> RapidApiProvider:
    base = make_handler([CONNECTING_ITINERARY])

    def handler(request: httpx.Request) -> httpx.Response:
        response = base(request)
        if remaining is not None:
            response.headers["x-ratelimit-requests-remaining"] = remaining
        return response

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://sky-scrapper.p.rapidapi.com"
    )
    return RapidApiProvider(
        "key", "sky-scrapper.p.rapidapi.com", client=client, place_cache_path=tmp_path / "p.json"
    )


async def test_health_reports_remaining_quota(client: AsyncClient, tmp_path) -> None:
    provider = build("143", tmp_path)
    await provider.search(REQUEST)
    set_provider(provider)
    try:
        body = (await client.get("/api/health")).json()
        assert body["provider_quota_remaining"] == 143
        assert body["provider"] == "rapidapi"
    finally:
        set_provider(None)
        await provider.aclose()


async def test_health_reports_an_exhausted_quota_as_zero(client: AsyncClient, tmp_path) -> None:
    """Zero must be reported as zero, not collapsed into 'unknown'."""
    provider = build("0", tmp_path)
    await provider.search(REQUEST)
    set_provider(provider)
    try:
        assert (await client.get("/api/health")).json()["provider_quota_remaining"] == 0
    finally:
        set_provider(None)
        await provider.aclose()


async def test_quota_is_absent_for_providers_that_do_not_meter(client: AsyncClient) -> None:
    """The mock provider has no quota; the field must be null, not zero."""
    body = (await client.get("/api/health")).json()

    assert body["provider"] == "mock"
    assert body["provider_quota_remaining"] is None


async def test_unparseable_quota_header_does_not_break_health(
    client: AsyncClient, tmp_path
) -> None:
    provider = build("unlimited", tmp_path)
    await provider.search(REQUEST)
    set_provider(provider)
    try:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["provider_quota_remaining"] is None
    finally:
        set_provider(None)
        await provider.aclose()
