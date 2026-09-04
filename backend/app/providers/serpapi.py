"""SerpApi Google Flights provider.

Google Flights is the widest view of published fares available through an API,
and SerpApi exposes it in the one shape this app needs: ``flights[]`` names
every leg with its own airports, and ``layovers[]`` names each connection. An
API that says "1 stop" without saying *where* is useless for hidden-city
detection, which is precisely a question about the stop.

Three details drive this implementation:

* **Times are naive local strings** (``"2026-09-15 07:12"``), with no offset.
  That is not a problem for layovers -- both sides of a connection are at the
  same airport, so the subtraction is in one timezone and comes out right --
  but it makes cross-timezone journey length unrecoverable from the timestamps.
  Every duration therefore comes from the API's own ``duration`` /
  ``total_duration`` minute counts, never from arithmetic on these datetimes.

* **The carrier code is only in the flight number.** ``airline`` is a display
  name ("British Airways"); the IATA code lives in ``flight_number``
  ("BA 301"). Everything downstream keys on the code, so it is split out here.

* **No results is not an error.** Google returning nothing for a thin market is
  an ordinary outcome the batch engine handles; it must not abort the run.

Docs: https://serpapi.com/google-flights-api
"""

from __future__ import annotations

import asyncio
import logging
import re
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
)

logger = logging.getLogger(__name__)

SEARCH_PATH = "/search"
ACCOUNT_PATH = "/account"

# travel_class in SerpApi's numbering.
CABIN_CLASSES = {
    "ECONOMY": 1,
    "PREMIUM_ECONOMY": 2,
    "BUSINESS": 3,
    "FIRST": 4,
}

ONE_WAY = 2
ANY_NUMBER_OF_STOPS = 0
NONSTOP_ONLY = 1

# SerpApi defaults to sort_by=1, Google's "Best" ranking, which trades price
# against convenience and quietly drops cheaper itineraries -- typically
# low-cost carriers with long layovers.
#
# That is not a display preference here, it is a correctness requirement. The
# cheapest A->B fare is the baseline every hidden-city saving is measured
# against. Ranked by "Best", AMM->DME on 2026-10-19 came back at JOD 366 when
# the real cheapest was JOD 241 via Sharjah -- so the baseline was overstated
# by more than a third, and any fare between the two would have been reported
# as a saving when it was in fact more expensive than simply booking the
# cheapest normal ticket.
SORT_BY_PRICE = 2

# "BA 301" -> ("BA", "301"). Codes are two characters, occasionally with a
# digit ("U2", "9W"), and the number follows after whitespace.
_FLIGHT_NUMBER = re.compile(r"^\s*(?P<carrier>[A-Z0-9]{2})\s*(?P<number>\d{1,4})\s*$")

_TIME_FORMAT = "%Y-%m-%d %H:%M"

# Phrases SerpApi uses when a market simply has nothing, as opposed to when the
# request itself was wrong. Matched case-insensitively against `error`.
_EMPTY_RESULT_PHRASES = (
    "hasn't returned any results",
    "has not returned any results",
    "no results",
)

# The account endpoint is not billed, but it is still an HTTP round trip; the
# badge does not need it fresher than this.
QUOTA_REFRESH_SECONDS = 300.0


class SerpApiProvider:
    """Live provider implementing the :class:`FlightProvider` protocol."""

    name = "serpapi"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._key = api_key or settings.serpapi_key
        if not self._key:
            raise ProviderError(
                "SerpApi key missing. Set SERPAPI_KEY, or set FLIGHT_PROVIDER=mock."
            )

        self._base_url = (base_url or settings.serpapi_base_url).rstrip("/")
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(settings.provider_timeout_seconds),
        )
        self._owns_client = client is None
        self._bucket = AsyncTokenBucket(settings.provider_requests_per_second)

        # Read by /api/health to show what is left on the plan.
        self.quota_remaining: int | None = None
        self._quota_checked_at = 0.0

    # ---------------------------------------------------------------- search
    async def search(self, request: SearchRequest) -> list[Offer]:
        body = await self._send(self._params(request))
        if body is None:
            return []

        offers: list[Offer] = []
        # best_flights is Google's own shortlist; other_flights is everything
        # else. Both are needed -- a hidden-city itinerary is by nature an
        # awkward one Google has no reason to promote.
        for group in ("best_flights", "other_flights"):
            for index, raw in enumerate(body.get(group) or []):
                parsed = self._parse_offer(raw, request, f"{group}-{index}")
                if parsed is not None:
                    offers.append(parsed)

        offers.sort(key=lambda offer: offer.price_total)
        await self._refresh_quota()
        return offers[: request.max_results]

    def _params(self, request: SearchRequest) -> dict[str, Any]:
        return {
            "engine": "google_flights",
            "api_key": self._key,
            "departure_id": request.origin,
            "arrival_id": request.destination,
            "outbound_date": request.departure_date.isoformat(),
            # Always one-way. A hidden-city itinerary cannot survive on a
            # round-trip ticket -- missing a leg cancels every leg after it --
            # so a return trip is priced here as two separate one-way searches.
            "type": ONE_WAY,
            "adults": request.adults,
            "travel_class": CABIN_CLASSES.get(request.cabin, 1),
            "currency": request.currency,
            "stops": NONSTOP_ONLY if request.non_stop else ANY_NUMBER_OF_STOPS,
            "sort_by": SORT_BY_PRICE,
            "hl": "en",
            # Slower, but returns what the Google Flights page itself shows.
            # On by default: with it off the same Saudia nonstop priced at
            # $146 instead of $131, and this site tells people to go and check
            # on Google. See settings.serpapi_deep_search.
            "deep_search": str(settings.serpapi_deep_search).lower(),
        }

    async def _send(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """One search with retries. ``None`` means "no flights", not "failed"."""
        last_error = "unknown error"

        for attempt in range(settings.provider_max_retries + 1):
            await self._bucket.acquire()
            try:
                response = await self._client.get(SEARCH_PATH, params=params)
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc}"
                await self._backoff(attempt)
                continue

            if response.status_code == httpx.codes.UNAUTHORIZED:
                raise ProviderError("SerpApi rejected the api key (401). Check SERPAPI_KEY.")

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                # Either the per-second concurrency limit or a spent plan, and
                # the body says which. Only the first is worth retrying.
                message = self._error_of(response)
                if "ran out" in message.lower() or "exceeded" in message.lower():
                    self.quota_remaining = 0
                    raise ProviderError(
                        f"SerpApi plan is exhausted: {message}. Wait for the plan "
                        "to reset, or upgrade it on the SerpApi dashboard."
                    )
                last_error = "rate limited"
                await self._backoff(attempt)
                continue

            if response.status_code >= 500:
                last_error = f"upstream {response.status_code}"
                await self._backoff(attempt)
                continue

            try:
                body = response.json()
            except ValueError:
                last_error = "response was not JSON"
                await self._backoff(attempt)
                continue

            error = str(body.get("error") or "")
            if error:
                if any(phrase in error.lower() for phrase in _EMPTY_RESULT_PHRASES):
                    logger.info(
                        "SerpApi has no flights for %s->%s on %s",
                        params["departure_id"],
                        params["arrival_id"],
                        params["outbound_date"],
                    )
                    return None
                raise ProviderError(f"SerpApi request failed: {error}")

            if response.status_code != httpx.codes.OK:
                raise ProviderError(
                    f"SerpApi request failed ({response.status_code}): {response.text[:200]}"
                )

            return body

        raise ProviderError(f"SerpApi request failed after retries: {last_error}")

    @staticmethod
    def _error_of(response: httpx.Response) -> str:
        try:
            return str(response.json().get("error") or response.text[:200])
        except ValueError:
            return response.text[:200]

    @staticmethod
    async def _backoff(attempt: int, base: float = 0.6) -> None:
        await asyncio.sleep(base * (2**attempt))

    # ----------------------------------------------------------------- quota
    async def _refresh_quota(self) -> None:
        """Update the remaining-search count, at most every few minutes.

        The account endpoint is not billed as a search. A failure here is
        deliberately swallowed: not knowing the balance must never turn a
        successful search into a failed one.
        """
        now = time.monotonic()
        if now - self._quota_checked_at < QUOTA_REFRESH_SECONDS:
            return
        self._quota_checked_at = now

        try:
            response = await self._client.get(ACCOUNT_PATH, params={"api_key": self._key})
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.debug("Could not read SerpApi account balance: %s", exc)
            return

        for field in ("total_searches_left", "plan_searches_left"):
            value = data.get(field)
            if isinstance(value, int):
                self.quota_remaining = value
                if value == 0:
                    logger.warning("SerpApi plan is spent: 0 searches left.")
                elif value <= 25:
                    logger.warning("SerpApi plan nearly spent: %d searches left.", value)
                return

    # --------------------------------------------------------------- parsing
    def _parse_offer(
        self, raw: dict[str, Any], request: SearchRequest, fallback_id: str
    ) -> Offer | None:
        # Google routinely returns itineraries it will not quote a price for.
        # That is not a malformed payload -- it is a flight this tool has
        # nothing to say about, since the whole product is price comparison.
        # Warning about it would cry wolf on every single search.
        if raw.get("price") is None:
            logger.debug("SerpApi offer has no price; skipping it.")
            return None

        try:
            segments = tuple(self._parse_segment(leg) for leg in raw["flights"])
            if not segments:
                return None
            price = float(raw["price"])
        except (KeyError, TypeError, ValueError) as exc:
            # Anything reaching here is genuinely wrong -- a missing leg, an
            # unreadable timestamp, a price that is not a number -- and is
            # worth seeing in the log.
            logger.warning("Skipping malformed SerpApi offer: %s", exc)
            return None

        # Trust the reported total; naive local times cannot produce it across
        # timezones. Fall back to the sum of the legs plus the layovers.
        total_duration = raw.get("total_duration")
        if not isinstance(total_duration, int) or total_duration <= 0:
            total_duration = sum(segment.duration_minutes for segment in segments) + sum(
                layover.get("duration", 0) or 0 for layover in (raw.get("layovers") or [])
            )

        itinerary = Itinerary(segments=segments, duration_minutes=total_duration)

        # The marketing carrier of the first leg is what the ticket is sold
        # under, which is the airline whose site the traveller is sent to.
        carriers = tuple(dict.fromkeys(s.carrier for s in segments if s.carrier))

        return Offer(
            provider=self.name,
            offer_id=str(raw.get("booking_token") or fallback_id)[:120],
            search_origin=request.origin,
            search_destination=request.destination,
            departure_date=request.departure_date,
            price_total=price,
            currency=request.currency,
            itineraries=(itinerary,),
            validating_carriers=carriers[:1],
            cabin=self._cabin_of(raw) or request.cabin,
            # Google Flights publishes no fare-bucket seat count.
            bookable_seats=None,
            raw=raw,
        )

    @classmethod
    def _parse_segment(cls, raw: dict[str, Any]) -> Segment:
        departure = raw["departure_airport"]
        arrival = raw["arrival_airport"]
        carrier, number = cls._split_flight_number(raw.get("flight_number"))

        duration = raw.get("duration")
        if not isinstance(duration, int) or duration <= 0:
            # Same-airport arithmetic is unavailable here (the two ends are in
            # different timezones), so this is a last resort that may be wrong
            # on long hauls. Preferred over dropping the offer entirely.
            duration = 0

        return Segment(
            origin=departure["id"],
            destination=arrival["id"],
            departure_at=cls._parse_time(departure["time"]),
            arrival_at=cls._parse_time(arrival["time"]),
            carrier=carrier,
            flight_number=number,
            duration_minutes=duration,
            aircraft=raw.get("airplane"),
            # Google exposes the operating carrier only as free text in
            # `extensions` ("Operated by ..."), which is not reliably a code.
            operating_carrier=None,
            cabin=(raw.get("travel_class") or "").upper().replace(" ", "_") or None,
        )

    @staticmethod
    def _parse_time(value: str) -> datetime:
        """``"2026-09-15 07:12"`` -> naive datetime in the airport's local time."""
        return datetime.strptime(value.strip(), _TIME_FORMAT)

    @staticmethod
    def _split_flight_number(value: str | None) -> tuple[str, str]:
        match = _FLIGHT_NUMBER.match((value or "").upper())
        if not match:
            return "", str(value or "").strip()
        return match.group("carrier"), match.group("number")

    @staticmethod
    def _cabin_of(raw: dict[str, Any]) -> str | None:
        for leg in raw.get("flights") or []:
            cabin = leg.get("travel_class")
            if cabin:
                return str(cabin).upper().replace(" ", "_")
        return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
