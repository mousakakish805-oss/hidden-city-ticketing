"""Amadeus Self-Service API provider.

Uses the v2 Flight Offers Search endpoint, whose responses carry full segment
detail (every intermediate airport, with arrival and departure times).  That
segment granularity is exactly what hidden-city detection needs -- an API that
only returns "1 stop" without naming the stop is useless here.

Docs: https://developers.amadeus.com/self-service/category/flights
"""

from __future__ import annotations

import asyncio
import logging
import time
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

TOKEN_PATH = "/v1/security/oauth2/token"
SEARCH_PATH = "/v2/shopping/flight-offers"
# Refresh a little before true expiry so an in-flight batch never 401s.
TOKEN_EXPIRY_MARGIN_SECONDS = 60.0


class AmadeusProvider:
    """Live provider implementing the :class:`FlightProvider` protocol."""

    name = "amadeus"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id or settings.amadeus_client_id
        self._client_secret = client_secret or settings.amadeus_client_secret
        if not self._client_id or not self._client_secret:
            raise ProviderError(
                "Amadeus credentials missing. Set AMADEUS_CLIENT_ID and "
                "AMADEUS_CLIENT_SECRET, or set FLIGHT_PROVIDER=mock."
            )

        self._base_url = (base_url or settings.amadeus_base_url).rstrip("/")
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(settings.provider_timeout_seconds),
            headers={"Accept": "application/json"},
        )
        self._owns_client = client is None

        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._bucket = AsyncTokenBucket(settings.provider_requests_per_second)

    # ------------------------------------------------------------------ auth
    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        async with self._token_lock:
            # Another coroutine may have refreshed while we waited.
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token

            await self._bucket.acquire()
            response = await self._client.post(
                TOKEN_PATH,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code != httpx.codes.OK:
                raise ProviderError(
                    f"Amadeus authentication failed ({response.status_code}): {response.text[:300]}"
                )

            payload = response.json()
            self._token = payload["access_token"]
            expires_in = float(payload.get("expires_in", 1799))
            self._token_expires_at = (
                time.monotonic() + max(expires_in - TOKEN_EXPIRY_MARGIN_SECONDS, 30.0)
            )
            return self._token

    # ---------------------------------------------------------------- search
    async def search(self, request: SearchRequest) -> list[Offer]:
        params: dict[str, Any] = {
            "originLocationCode": request.origin,
            "destinationLocationCode": request.destination,
            "departureDate": request.departure_date.isoformat(),
            "adults": request.adults,
            "currencyCode": request.currency,
            "travelClass": request.cabin,
            "max": min(request.max_results, 250),
        }
        if request.non_stop:
            params["nonStop"] = "true"

        payload = await self._get_with_retries(SEARCH_PATH, params)
        dictionaries = payload.get("dictionaries") or {}
        offers: list[Offer] = []
        for raw_offer in payload.get("data") or []:
            parsed = self._parse_offer(raw_offer, request, dictionaries)
            if parsed is not None:
                offers.append(parsed)

        offers.sort(key=lambda offer: offer.price_total)
        return offers

    async def _get_with_retries(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: str = "unknown error"

        for attempt in range(settings.provider_max_retries + 1):
            token = await self._access_token()
            await self._bucket.acquire()
            try:
                response = await self._client.get(
                    path, params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc}"
                await self._backoff(attempt)
                continue

            if response.status_code == httpx.codes.OK:
                return response.json()

            if response.status_code == httpx.codes.UNAUTHORIZED:
                # Force a token refresh and try again.
                self._token = None
                self._token_expires_at = 0.0
                last_error = "unauthorized"
                await self._backoff(attempt)
                continue

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                last_error = "rate limited"
                await self._backoff(attempt, base=1.5)
                continue

            if response.status_code == httpx.codes.BAD_REQUEST:
                # Unserved market or malformed query: an empty result, not a
                # failure the batch engine should retry.
                logger.info(
                    "Amadeus rejected %s -> %s: %s",
                    params.get("originLocationCode"),
                    params.get("destinationLocationCode"),
                    response.text[:200],
                )
                return {"data": []}

            if response.status_code >= 500:
                last_error = f"upstream {response.status_code}"
                await self._backoff(attempt)
                continue

            raise ProviderError(
                f"Amadeus request failed ({response.status_code}): {response.text[:300]}"
            )

        raise ProviderError(f"Amadeus request failed after retries: {last_error}")

    @staticmethod
    async def _backoff(attempt: int, base: float = 0.6) -> None:
        await asyncio.sleep(base * (2**attempt))

    # ----------------------------------------------------------- parsing ---
    def _parse_offer(
        self,
        raw: dict[str, Any],
        request: SearchRequest,
        dictionaries: dict[str, Any],
    ) -> Offer | None:
        try:
            itineraries = tuple(
                self._parse_itinerary(itinerary, dictionaries)
                for itinerary in raw["itineraries"]
            )
            if not itineraries or not itineraries[0].segments:
                return None

            price_block = raw.get("price") or {}
            total = float(price_block.get("grandTotal") or price_block["total"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping unparseable Amadeus offer %s: %s", raw.get("id"), exc)
            return None

        cabin = self._cabin_of(raw)

        return Offer(
            provider=self.name,
            offer_id=str(raw.get("id", "")),
            search_origin=request.origin,
            search_destination=request.destination,
            departure_date=request.departure_date,
            price_total=total,
            currency=price_block.get("currency", request.currency),
            itineraries=itineraries,
            validating_carriers=tuple(raw.get("validatingAirlineCodes") or ()),
            cabin=cabin or request.cabin,
            bookable_seats=raw.get("numberOfBookableSeats"),
            raw=raw,
        )

    def _parse_itinerary(
        self, raw: dict[str, Any], dictionaries: dict[str, Any]
    ) -> Itinerary:
        segments = tuple(
            self._parse_segment(segment, dictionaries) for segment in raw["segments"]
        )
        duration = parse_iso_duration(raw.get("duration"))
        if not duration and segments:
            duration = int(
                (segments[-1].arrival_at - segments[0].departure_at).total_seconds() // 60
            )
        return Itinerary(segments=segments, duration_minutes=duration)

    @staticmethod
    def _parse_segment(raw: dict[str, Any], dictionaries: dict[str, Any]) -> Segment:
        departure, arrival = raw["departure"], raw["arrival"]
        departure_at = datetime.fromisoformat(departure["at"])
        arrival_at = datetime.fromisoformat(arrival["at"])
        duration = parse_iso_duration(raw.get("duration")) or int(
            (arrival_at - departure_at).total_seconds() // 60
        )
        aircraft = (raw.get("aircraft") or {}).get("code")
        aircraft_names = (dictionaries.get("aircraft") or {}) if dictionaries else {}

        return Segment(
            origin=departure["iataCode"],
            destination=arrival["iataCode"],
            departure_at=departure_at,
            arrival_at=arrival_at,
            carrier=raw["carrierCode"],
            flight_number=str(raw.get("number", "")),
            duration_minutes=duration,
            aircraft=aircraft_names.get(aircraft, aircraft),
            operating_carrier=(raw.get("operating") or {}).get("carrierCode"),
        )

    @staticmethod
    def _cabin_of(raw: dict[str, Any]) -> str | None:
        """Cabin actually sold, from the first traveller's fare details.

        Baggage allowances are deliberately not read: this app reports fares,
        not what each ticket includes.
        """
        traveler_pricings = raw.get("travelerPricings") or []
        if not traveler_pricings:
            return None
        fare_details = traveler_pricings[0].get("fareDetailsBySegment") or []
        if not fare_details:
            return None
        return fare_details[0].get("cabin")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
