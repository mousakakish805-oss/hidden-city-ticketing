"""RapidAPI "Air Scraper" provider (Skyscanner-derived).

Three things make this listing different from Duffel and Amadeus, and all three
shape the code:

**Airports are addressed by entity ID, not IATA.** Every search needs a
``skyId``/``entityId`` pair per airport, fetched from a separate endpoint. Left
naive that would double the request count, so resolutions are cached in memory
and on disk -- airport IDs do not change, and on a free tier every call counts.

**Self-transfer itineraries must be excluded.** The API happily returns
journeys stitched from separate tickets. Hidden-city ticketing requires *one*
ticket: on separate tickets you collect bags and re-check in, and skipping the
final leg does not save you anything because you never bought it as one fare.
Including them would produce recommendations that are simply wrong.

**Results arrive incomplete.** Skyscanner-style searches poll, so the first
response often carries ``context.status == "incomplete"``. We use what is
there rather than burning quota on polling.

Because this is a scraped, unofficial listing whose shape changes without
notice, parsing is deliberately defensive: a field that moves should cost one
offer, not the whole run. Verify against your key with::

    python scripts/probe_rapidapi.py --host <host> --path /api/v1/flights/searchFlights ...
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import BACKEND_DIR, settings
from app.core.ratelimit import AsyncTokenBucket
from app.providers.base import (
    Itinerary,
    Offer,
    ProviderError,
    SearchRequest,
    Segment,
)

logger = logging.getLogger(__name__)

SEARCH_AIRPORT_PATH = "/api/v1/flights/searchAirport"
SEARCH_FLIGHTS_PATH = "/api/v1/flights/searchFlights"

CABIN_CLASSES = {
    "ECONOMY": "economy",
    "PREMIUM_ECONOMY": "premium_economy",
    "BUSINESS": "business",
    "FIRST": "first",
}

# Airport IDs are stable, so resolutions persist between runs. On a free tier
# this is the difference between one lookup ever and one per search.
PLACE_CACHE_PATH = BACKEND_DIR / ".cache" / "rapidapi_places.json"


class Place:
    """A resolved airport: the pair of identifiers the search endpoint wants."""

    __slots__ = ("sky_id", "entity_id")

    def __init__(self, sky_id: str, entity_id: str) -> None:
        self.sky_id = sky_id
        self.entity_id = entity_id

    def to_dict(self) -> dict[str, str]:
        return {"sky_id": self.sky_id, "entity_id": self.entity_id}


class RapidApiProvider:
    """Air Scraper via RapidAPI, implementing the FlightProvider protocol."""

    name = "rapidapi"

    def __init__(
        self,
        api_key: str | None = None,
        host: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        place_cache_path: Path | None = None,
    ) -> None:
        self._key = api_key or settings.rapidapi_key
        self._host = host or settings.rapidapi_host
        if not self._key or not self._host:
            raise ProviderError(
                "RapidAPI credentials missing. Set RAPIDAPI_KEY and RAPIDAPI_HOST, "
                "or set FLIGHT_PROVIDER=mock."
            )

        self._client = client or httpx.AsyncClient(
            base_url=f"https://{self._host}",
            timeout=httpx.Timeout(settings.provider_timeout_seconds),
        )
        self._owns_client = client is None
        # burst=1: free plans reject even a small burst, and a 429 costs more
        # than the second it would have saved.
        self._bucket = AsyncTokenBucket(settings.rapidapi_requests_per_second, burst=1)
        self._quota_remaining: str | None = None

        self._cache_path = place_cache_path or PLACE_CACHE_PATH
        self._places: dict[str, Place] = self._load_places()
        self._place_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        return {"x-rapidapi-key": self._key, "x-rapidapi-host": self._host}

    # ------------------------------------------------------------ place cache
    def _load_places(self) -> dict[str, Place]:
        if not self._cache_path.is_file():
            return {}
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return {
                code: Place(entry["sky_id"], entry["entity_id"]) for code, entry in raw.items()
            }
        except (ValueError, KeyError, TypeError, OSError):
            logger.warning("Discarding unreadable RapidAPI place cache")
            return {}

    def _save_places(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps({code: p.to_dict() for code, p in self._places.items()}, indent=2),
                encoding="utf-8",
            )
        except OSError:  # pragma: no cover - a read-only FS must not break search
            logger.debug("Could not persist RapidAPI place cache", exc_info=True)

    async def _resolve_place(self, iata: str) -> Place | None:
        """IATA code -> (skyId, entityId), cached forever once known."""
        code = iata.upper()
        if code in self._places:
            return self._places[code]

        async with self._place_lock:
            # Another coroutine may have resolved it while we waited.
            if code in self._places:
                return self._places[code]

            body = await self._get(SEARCH_AIRPORT_PATH, {"query": code, "locale": "en-US"})
            if body is None:
                return None

            for entry in body.get("data") or []:
                params = (entry.get("navigation") or {}).get("relevantFlightParams") or {}
                sky_id = entry.get("skyId") or params.get("skyId")
                entity_id = entry.get("entityId") or params.get("entityId")
                # Only accept an exact airport match: a city-level entity would
                # silently search the wrong thing.
                if sky_id and entity_id and str(sky_id).upper() == code:
                    place = Place(str(sky_id), str(entity_id))
                    self._places[code] = place
                    self._save_places()
                    return place

            logger.info("RapidAPI could not resolve airport %s", code)
            return None

    # ---------------------------------------------------------------- search
    async def search(self, request: SearchRequest) -> list[Offer]:
        origin = await self._resolve_place(request.origin)
        destination = await self._resolve_place(request.destination)
        if origin is None or destination is None:
            return []

        params = {
            "originSkyId": origin.sky_id,
            "destinationSkyId": destination.sky_id,
            "originEntityId": origin.entity_id,
            "destinationEntityId": destination.entity_id,
            "date": request.departure_date.isoformat(),
            "cabinClass": CABIN_CLASSES.get(request.cabin, "economy"),
            "adults": request.adults,
            # "best" is accepted by every variant of this listing; results are
            # re-sorted by price locally anyway.
            "sortBy": "best",
            "currency": request.currency,
            "market": "en-US",
            "countryCode": "US",
        }

        body = await self._get(SEARCH_FLIGHTS_PATH, params)
        if body is None:
            return []

        data = await self._complete(body, params, request)

        offers: list[Offer] = []
        for raw in data.get("itineraries") or []:
            parsed = self._parse_itinerary(raw, request)
            if parsed is not None:
                offers.append(parsed)

        offers.sort(key=lambda offer: offer.price_total)
        return offers[: request.max_results]

    async def _complete(
        self,
        body: dict[str, Any],
        params: dict[str, Any],
        request: SearchRequest,
    ) -> dict[str, Any]:
        """Re-issue the search until it returns a complete result set.

        This is required for correctness, not a nicety. The first call for a
        route *starts* a search server-side and returns a fragment: a real
        AMM->IST search came back with one 19-hour routing via Dubai and
        ``direct.isPresent = false``, for a pair two airlines fly nonstop
        daily. The identical request moments later returned nine itineraries
        including the direct flights.

        A truncated response does not just hide options, it corrupts the
        *baseline* every reported saving is measured against. Fewer candidate
        destinations with complete data beats more candidates with fragments.

        Note this re-issues ``searchFlights`` rather than calling a dedicated
        polling endpoint -- this listing has none (``searchIncomplete`` returns
        404). The search is keyed server-side by its parameters, so repeating
        the request is what collects the finished result.

        Completion is judged by **result count, not by ``context.status``**.
        Observed behaviour: an AMM->SKP search returned 8 itineraries on the
        first retry and the identical 8 on two further retries, while the
        status field stayed ``"incomplete"`` throughout. Trusting that flag
        would spend the whole retry budget on every single search -- real money
        on a metered plan.
        """
        data = body.get("data") or {}
        best = len(data.get("itineraries") or [])

        for attempt in range(settings.rapidapi_max_polls):
            # Wait longer each time: these searches take several seconds to
            # settle, so a fixed short delay retries before anything is ready.
            await asyncio.sleep(settings.rapidapi_poll_delay_seconds * (attempt + 1))

            polled = await self._get(SEARCH_FLIGHTS_PATH, params)
            if polled is None:
                break

            polled_data = polled.get("data") or {}
            count = len(polled_data.get("itineraries") or [])
            logger.debug(
                "Retry %d for %s->%s: itineraries %d -> %d",
                attempt + 1,
                request.origin,
                request.destination,
                best,
                count,
            )

            # A later response must never leave the search worse off.
            if count > best:
                data, best = polled_data, count
            elif best:
                # Stopped growing and we have results: the search has settled,
                # whatever the status field claims.
                break

        if not best:
            logger.info(
                "No itineraries for %s->%s after %d retries.",
                request.origin,
                request.destination,
                settings.rapidapi_max_polls,
            )
        return data

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """One request with retries. ``None`` means "no result", not "failure"."""
        last_error = "unknown error"

        for attempt in range(settings.provider_max_retries + 1):
            await self._bucket.acquire()
            try:
                response = await self._client.get(path, params=params, headers=self._headers())
            except httpx.HTTPError as exc:
                last_error = f"transport error: {exc}"
                await self._backoff(attempt)
                continue

            self._record_quota(response)

            if response.status_code == httpx.codes.OK:
                try:
                    return response.json()
                except ValueError:
                    logger.warning("RapidAPI returned non-JSON for %s", path)
                    return None

            if response.status_code == httpx.codes.UNAUTHORIZED:
                raise ProviderError(
                    "RapidAPI rejected the key (401). Check RAPIDAPI_KEY."
                )

            if response.status_code == httpx.codes.FORBIDDEN:
                # RapidAPI uses 403 both for "not subscribed" and for a spent
                # quota, and the difference matters a lot to the operator.
                raise ProviderError(
                    "RapidAPI returned 403. Either the key is not subscribed to "
                    f"'{self._host}', or the plan's monthly quota is exhausted. "
                    "Check the Usage tab on the RapidAPI dashboard."
                )

            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                # RapidAPI returns 429 for two very different situations, and
                # the remaining-requests header is what tells them apart.
                # Retrying an exhausted quota can never succeed -- it just
                # burns fifteen seconds before failing anyway.
                if self._quota_remaining == "0":
                    raise ProviderError(
                        "RapidAPI monthly quota is exhausted (0 requests remaining). "
                        "Wait for the plan to reset, or upgrade it on the RapidAPI "
                        "dashboard. Set FLIGHT_PROVIDER=mock to keep the app usable "
                        "in the meantime."
                    )

                wait = self._retry_after(response, attempt)
                logger.info("RapidAPI rate limited; waiting %.1fs before retry", wait)
                last_error = "rate limited"
                await asyncio.sleep(wait)
                continue

            if response.status_code >= 500:
                last_error = f"upstream {response.status_code}"
                await self._backoff(attempt)
                continue

            logger.info(
                "RapidAPI %s for %s: %s", response.status_code, path, response.text[:200]
            )
            return None

        raise ProviderError(f"RapidAPI request failed after retries: {last_error}")

    @staticmethod
    async def _backoff(attempt: int, base: float = 0.6) -> None:
        await asyncio.sleep(base * (2**attempt))

    @staticmethod
    def _retry_after(response: httpx.Response, attempt: int) -> float:
        """How long to wait after a 429, preferring what the server told us."""
        for header in ("retry-after", "x-ratelimit-rate-limit-reset", "ratelimit-reset"):
            raw = response.headers.get(header)
            if raw:
                try:
                    # Clamp: a plan-level reset can be hours away, and blocking
                    # a search that long is worse than returning nothing.
                    return max(1.0, min(float(raw), 30.0))
                except ValueError:
                    continue
        return 2.0 * (2**attempt)

    def _record_quota(self, response: httpx.Response) -> None:
        """Track remaining monthly quota so it can be surfaced, not guessed at."""
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if remaining is None:
            return
        self._quota_remaining = remaining
        try:
            left = int(remaining)
        except ValueError:
            return
        if left <= 25:
            logger.warning(
                "RapidAPI quota nearly exhausted: %s requests remaining this period.", left
            )

    @property
    def quota_remaining(self) -> str | None:
        """Requests left this period, as last reported by the API."""
        return self._quota_remaining

    # --------------------------------------------------------------- parsing
    def _parse_itinerary(self, raw: dict[str, Any], request: SearchRequest) -> Offer | None:
        # Separate tickets cannot carry a hidden-city fare: you re-check in at
        # the stop, and there is no single fare to undercut.
        if raw.get("isSelfTransfer") or raw.get("isProtectedSelfTransfer"):
            return None

        try:
            price = (raw.get("price") or {}).get("raw")
            if price is None:
                return None
            legs = raw.get("legs") or []
            itineraries = tuple(self._parse_leg(leg) for leg in legs)
            if not itineraries or not itineraries[0].segments:
                return None
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping unparseable RapidAPI itinerary %s: %s", raw.get("id"), exc)
            return None

        carrier = self._marketing_carrier(legs[0])
        return Offer(
            provider=self.name,
            offer_id=str(raw.get("id", "")),
            search_origin=request.origin,
            search_destination=request.destination,
            departure_date=request.departure_date,
            price_total=float(price),
            currency=request.currency,
            itineraries=itineraries,
            validating_carriers=(carrier,) if carrier else (),
            cabin=request.cabin,
            bookable_seats=None,
            raw=raw,
        )

    def _parse_leg(self, raw: dict[str, Any]) -> Itinerary:
        segments = tuple(
            self._parse_segment(segment) for segment in (raw.get("segments") or [])
        )
        duration = int(raw.get("durationInMinutes") or 0)
        if not duration and segments:
            duration = int(
                (segments[-1].arrival_at - segments[0].departure_at).total_seconds() // 60
            )
        return Itinerary(segments=segments, duration_minutes=duration)

    def _parse_segment(self, raw: dict[str, Any]) -> Segment:
        departure_at = self._parse_datetime(raw["departure"])
        arrival_at = self._parse_datetime(raw["arrival"])
        duration = int(raw.get("durationInMinutes") or 0) or int(
            (arrival_at - departure_at).total_seconds() // 60
        )
        marketing = raw.get("marketingCarrier") or {}
        operating = raw.get("operatingCarrier") or {}

        return Segment(
            origin=self._place_code(raw.get("origin")),
            destination=self._place_code(raw.get("destination")),
            departure_at=departure_at,
            arrival_at=arrival_at,
            # alternateId is the IATA code; the numeric `id` is Skyscanner's own.
            carrier=str(marketing.get("alternateId") or ""),
            flight_number=str(raw.get("flightNumber") or ""),
            duration_minutes=duration,
            aircraft=None,
            operating_carrier=str(operating.get("alternateId") or "") or None,
        )

    @staticmethod
    def _place_code(place: dict[str, Any] | None) -> str:
        """Airport IATA code, tolerating the several field names in use."""
        if not place:
            return ""
        for key in ("displayCode", "flightPlaceId", "id", "skyId"):
            value = place.get(key)
            if isinstance(value, str) and len(value) == 3 and value.isalpha():
                return value.upper()
        return ""

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _marketing_carrier(leg: dict[str, Any]) -> str | None:
        marketing = ((leg.get("carriers") or {}).get("marketing")) or []
        if marketing and isinstance(marketing[0], dict):
            code = marketing[0].get("alternateId")
            if code:
                return str(code)
        return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
