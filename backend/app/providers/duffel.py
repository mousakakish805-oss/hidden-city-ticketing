"""Duffel Flights API provider.

Duffel differs from Amadeus in three ways that shape this implementation:

* **Static bearer token**, not an OAuth client-credentials exchange. No token
  refresh, no expiry handling.
* **Two-step search.** You create an *offer request*, then read the offers it
  produced. We deliberately pass ``return_offers=false`` and fetch separately
  with ``limit`` and ``sort``: a busy market can return hundreds of offers, and
  a fan-out of a dozen probes would otherwise pull megabytes we throw away.
* **Versioned by header.** Every request must carry ``Duffel-Version``; the API
  changes behaviour without it.

What matters for this app is that offers expose ``slices[].segments[]`` with
every intermediate airport named -- without that, hidden-city detection is
impossible.

Docs: https://duffel.com/docs/api
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.core.ratelimit import AsyncTokenBucket
from app.providers.base import (
    Itinerary,
    Offer,
    ProviderError,
    SearchRequest,
    Segment,
    parse_iso_duration,
)

logger = logging.getLogger(__name__)

OFFER_REQUESTS_PATH = "/air/offer_requests"
OFFERS_PATH = "/air/offers"

CABIN_CLASSES = {
    "ECONOMY": "economy",
    "PREMIUM_ECONOMY": "premium_economy",
    "BUSINESS": "business",
    "FIRST": "first",
}

# Duffel allows at most 2. We need at least 1 for a hidden city to exist at all.
MAX_CONNECTIONS = 2

# "Duffel Airways" -- the fabricated carrier that only exists in the sandbox.
TEST_AIRLINE_CODE = "ZZ"


class DuffelProvider:
    """Live provider implementing the :class:`FlightProvider` protocol."""

    name = "duffel"

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = access_token or settings.duffel_access_token
        if not self._token:
            raise ProviderError(
                "Duffel access token missing. Set DUFFEL_ACCESS_TOKEN, or set "
                "FLIGHT_PROVIDER=mock."
            )

        self._base_url = (base_url or settings.duffel_base_url).rstrip("/")
        self._api_version = api_version or settings.duffel_api_version
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(settings.provider_timeout_seconds),
        )
        self._owns_client = client is None
        self._bucket = AsyncTokenBucket(settings.provider_requests_per_second)

    @property
    def is_live_mode(self) -> bool:
        """Whether this token hits real inventory rather than Duffel's sandbox."""
        return self._token.startswith("duffel_live")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Duffel-Version": self._api_version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ---------------------------------------------------------------- search
    async def search(self, request: SearchRequest) -> list[Offer]:
        offer_request_id = await self._create_offer_request(request)
        if offer_request_id is None:
            return []

        raw_offers = await self._fetch_offers(offer_request_id, request)
        offers: list[Offer] = []
        for raw in raw_offers:
            parsed = self._parse_offer(raw, request)
            if parsed is None or self._is_test_airline(parsed):
                continue
            offers.append(parsed)

        offers.sort(key=lambda offer: offer.price_total)
        return offers

    def _is_test_airline(self, offer: Offer) -> bool:
        """Whether this is Duffel's synthetic sandbox carrier.

        Sandbox responses mix real airline schedules with one fabricated
        "Duffel Airways" nonstop per market, always undercutting everything
        around it. Since price comparison is the entire product, leaving that
        in would make every search report a bogus cheapest fare -- and, worse,
        make it the baseline that real options are measured against.
        """
        if not settings.duffel_drop_test_airline or self.is_live_mode:
            return False
        return offer.primary_carrier == TEST_AIRLINE_CODE

    async def _create_offer_request(self, request: SearchRequest) -> str | None:
        payload = {
            "data": {
                "slices": [
                    {
                        "origin": request.origin,
                        "destination": request.destination,
                        "departure_date": request.departure_date.isoformat(),
                    }
                ],
                # One entry per traveller; Duffel prices per passenger.
                "passengers": [{"type": "adult"} for _ in range(request.adults)],
                "cabin_class": CABIN_CLASSES.get(request.cabin, "economy"),
                "max_connections": 0 if request.non_stop else MAX_CONNECTIONS,
            }
        }

        body = await self._send(
            "POST",
            OFFER_REQUESTS_PATH,
            json=payload,
            # Offers are fetched separately so we can bound the payload.
            params={"return_offers": "false"},
        )
        if body is None:
            return None
        return (body.get("data") or {}).get("id")

    async def _fetch_offers(
        self, offer_request_id: str, request: SearchRequest
    ) -> list[dict[str, Any]]:
        body = await self._send(
            "GET",
            OFFERS_PATH,
            params={
                "offer_request_id": offer_request_id,
                "limit": min(request.max_results, 200),
                "sort": "total_amount",
            },
        )
        if body is None:
            return []
        return body.get("data") or []

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """One request with retries. ``None`` means "no result", not "failure"."""
        last_error = "unknown error"

        for attempt in range(settings.provider_max_retries + 1):
            await self._bucket.acquire()
            try:
                response = await self._client.request(
                    method, path, json=json, params=params, headers=self._headers()
                )
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc}"
                await self._backoff(attempt)
                continue

            if response.status_code in (httpx.codes.OK, httpx.codes.CREATED):
                return response.json()

            if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
                raise ProviderError(
                    f"Duffel rejected the access token ({response.status_code}). "
                    "Check DUFFEL_ACCESS_TOKEN."
                )

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                # Duffel tells us exactly how long to wait; use it when present.
                reset = response.headers.get("ratelimit-reset")
                last_error = "rate limited"
                await self._backoff(attempt, base=self._reset_delay(reset))
                continue

            if response.status_code in (
                httpx.codes.UNPROCESSABLE_ENTITY,
                httpx.codes.BAD_REQUEST,
                httpx.codes.NOT_FOUND,
            ):
                # An unserved market or a route Duffel will not quote. That is
                # an empty result, not a failure the batch engine should retry.
                logger.info(
                    "Duffel returned %s for %s: %s",
                    response.status_code,
                    path,
                    self._describe_errors(response),
                )
                return None

            if response.status_code >= 500:
                last_error = f"upstream {response.status_code}"
                await self._backoff(attempt)
                continue

            raise ProviderError(
                f"Duffel request failed ({response.status_code}): "
                f"{self._describe_errors(response)}"
            )

        raise ProviderError(f"Duffel request failed after retries: {last_error}")

    @staticmethod
    def _reset_delay(reset_header: str | None) -> float:
        try:
            return max(0.5, min(float(reset_header or 1.0), 10.0))
        except (TypeError, ValueError):
            return 1.0

    @staticmethod
    async def _backoff(attempt: int, base: float = 0.6) -> None:
        await asyncio.sleep(base * (2**attempt))

    @staticmethod
    def _describe_errors(response: httpx.Response) -> str:
        """Duffel returns structured errors; surface the useful part."""
        try:
            errors = response.json().get("errors") or []
        except ValueError:
            return response.text[:200]
        if not errors:
            return response.text[:200]
        return "; ".join(
            f"{error.get('title', '?')}: {error.get('message', '')}" for error in errors[:3]
        )

    # ---------------------------------------------------------------- parsing
    def _parse_offer(self, raw: dict[str, Any], request: SearchRequest) -> Offer | None:
        try:
            slices = raw["slices"]
            itineraries = tuple(self._parse_slice(item) for item in slices)
            if not itineraries or not itineraries[0].segments:
                return None
            total = float(raw["total_amount"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping unparseable Duffel offer %s: %s", raw.get("id"), exc)
            return None

        owner = (raw.get("owner") or {}).get("iata_code")
        return Offer(
            provider=self.name,
            offer_id=str(raw.get("id", "")),
            search_origin=request.origin,
            search_destination=request.destination,
            departure_date=request.departure_date,
            price_total=total,
            currency=raw.get("total_currency", request.currency),
            itineraries=itineraries,
            validating_carriers=(owner,) if owner else (),
            cabin=self._cabin_of(raw) or request.cabin,
            # Duffel does not publish a remaining-seat count on offers.
            bookable_seats=None,
            raw=raw,
        )

    def _parse_slice(self, raw: dict[str, Any]) -> Itinerary:
        segments = tuple(self._parse_segment(segment) for segment in raw["segments"])
        duration = parse_iso_duration(raw.get("duration"))
        if not duration and segments:
            duration = int(
                (segments[-1].arrival_at - segments[0].departure_at).total_seconds() // 60
            )
        return Itinerary(segments=segments, duration_minutes=duration)

    @staticmethod
    def _parse_segment(raw: dict[str, Any]) -> Segment:
        departure_at = datetime.fromisoformat(raw["departing_at"])
        arrival_at = datetime.fromisoformat(raw["arriving_at"])
        duration = parse_iso_duration(raw.get("duration")) or int(
            (arrival_at - departure_at).total_seconds() // 60
        )
        marketing = raw.get("marketing_carrier") or {}
        operating = raw.get("operating_carrier") or {}
        aircraft = raw.get("aircraft") or {}

        return Segment(
            origin=raw["origin"]["iata_code"],
            destination=raw["destination"]["iata_code"],
            departure_at=departure_at,
            arrival_at=arrival_at,
            carrier=marketing.get("iata_code", ""),
            flight_number=str(raw.get("marketing_carrier_flight_number", "")),
            duration_minutes=duration,
            aircraft=aircraft.get("iata_code"),
            operating_carrier=operating.get("iata_code"),
        )

    @staticmethod
    def _cabin_of(raw: dict[str, Any]) -> str | None:
        """Cabin sold, read from the first segment's passenger entry.

        Baggage allowances sit right beside this in the payload and are
        deliberately not read: this app reports fares, not what a ticket
        includes.
        """
        for slice_ in raw.get("slices") or []:
            for segment in slice_.get("segments") or []:
                for passenger in segment.get("passengers") or []:
                    cabin = passenger.get("cabin_class")
                    if cabin:
                        return str(cabin).upper()
        return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
