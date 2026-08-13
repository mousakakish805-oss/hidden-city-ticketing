"""Deterministic synthetic flight provider.

Lets the whole application run end-to-end with zero credentials, and -- more
importantly -- lets the anomaly detector be tested against a *known* ground
truth.

Routings are not invented: nonstop service and connecting hubs both come from
the real route graph, so a synthetic itinerary only ever uses city pairs that
are actually flown, by carriers that actually serve those airports.

The pricing model reproduces the market structure that creates hidden-city
opportunities:

    Through-fares are priced against the origin-destination market, not as the
    sum of their legs.

So a hub B dominated by one carrier (IST, demand index 1.25) is expensive to
fly *to*, while a thin market C behind it (SKP, 0.88) is priced competitively
against every other carrier that could get you there. Result: A->C via B
undercuts A->B, which is exactly the anomaly the detector must find.

Seeded from the query itself, so identical searches return identical results.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from random import Random

from app.core.geo import detour_ratio, haversine_km
from app.data.airports import Airport, get_airport
from app.data.routes import common_operator, has_route, one_stop_hubs, route_operators
from app.providers.base import Itinerary, Offer, SearchRequest, Segment

# Fares fall as itineraries get less convenient.
STOP_MULTIPLIER: dict[int, float] = {0: 1.16, 1: 1.00, 2: 0.90}

# Carriers price their brand differently for the same seat. Anything unlisted
# is treated as a neutral full-service carrier.
CARRIER_MULTIPLIER: dict[str, float] = {
    "TK": 0.94, "PC": 0.80, "W6": 0.74, "FR": 0.70, "U2": 0.78, "VY": 0.80,
    "RJ": 1.04, "MS": 0.90, "QR": 1.02, "EK": 1.06, "EY": 0.98, "LH": 1.14,
    "AF": 1.10, "KL": 1.08, "BA": 1.12, "LX": 1.16, "OS": 1.08, "A3": 0.96,
    "SU": 0.90, "ET": 0.92, "AI": 0.88, "SQ": 1.12, "CX": 1.08, "QF": 1.10,
}
DEFAULT_CARRIER = "ZZ"

AIRCRAFT_POOL = ("32N", "738", "789", "77W", "320", "321", "E90", "223")


def _stable_seed(*parts: object) -> int:
    """Process-independent seed (``hash()`` on str is salted per interpreter)."""
    digest = hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8)
    return int.from_bytes(digest.digest(), "big")


def _flight_minutes(distance_km: float) -> int:
    """Block time: taxi + climb/descent overhead + cruise at ~750 km/h."""
    return int(35 + distance_km / 12.5)


def _base_market_fare(origin: Airport, destination: Airport, distance_km: float) -> float:
    """Fare for the *origin-destination market*, before itinerary adjustments.

    This is the crux of the model: the fare tracks where you are ticketed to,
    not how far the aircraft physically carries you.
    """
    distance_cost = 28.0 + 0.075 * (max(distance_km, 50.0) ** 0.95)
    demand = destination.demand_index
    # A pricey origin lifts fares, but less than the destination market does.
    origin_pressure = 1.0 + (origin.demand_index - 1.0) * 0.4
    # Well-served city pairs attract competitors, which suppresses fares.
    competition = 1.0 - 0.035 * min(origin.hub_tier, destination.hub_tier)
    return distance_cost * demand * origin_pressure * competition


def _advance_purchase_factor(departure: date, today: date) -> float:
    """Classic booking curve: cheap in the middle, expensive last-minute."""
    days_out = (departure - today).days
    if days_out <= 2:
        return 1.85
    if days_out <= 7:
        return 1.45
    if days_out <= 21:
        return 1.12
    if days_out <= 90:
        return 1.0
    return 1.06  # schedules barely loaded this far out; fares are unrefined


class MockFlightProvider:
    """Synthetic provider implementing the :class:`FlightProvider` protocol."""

    name = "mock"

    def __init__(self, *, today: date | None = None) -> None:
        self._today = today or date.today()

    async def search(self, request: SearchRequest) -> list[Offer]:
        origin = get_airport(request.origin)
        destination = get_airport(request.destination)
        if origin is None or destination is None or origin.iata == destination.iata:
            return []

        rng = Random(
            _stable_seed(
                "mock-v2", request.origin, request.destination,
                request.departure_date, request.cabin, request.adults,
            )
        )
        direct_km = haversine_km(origin.lat, origin.lon, destination.lat, destination.lon)
        market_fare = _base_market_fare(origin, destination, direct_km)
        market_fare *= _advance_purchase_factor(request.departure_date, self._today)

        offers: list[Offer] = []

        # -- nonstop, only where the route graph says one exists ---------------
        if has_route(origin.iata, destination.iata):
            offers.append(
                self._build_offer(
                    request, rng, market_fare,
                    path=(origin, destination), stops=0, index=len(offers),
                )
            )

        # -- one-stop itineraries over hubs that really connect the two --------
        hubs = self._connecting_hubs(origin, destination, rng)
        for hub in hubs:
            offers.append(
                self._build_offer(
                    request, rng, market_fare,
                    path=(origin, hub, destination), stops=1, index=len(offers),
                )
            )

        # -- one double-connection for long thin markets -----------------------
        # Held to the same single-operator rule as the one-stop paths above.
        if direct_km > 3000 and len(hubs) >= 2 and rng.random() < 0.6:
            first, second = hubs[0], hubs[1]
            double_hop = (origin, first, second, destination)
            legs = [
                (double_hop[i].iata, double_hop[i + 1].iata)
                for i in range(len(double_hop) - 1)
            ]
            if common_operator(legs) is not None:
                offers.append(
                    self._build_offer(
                        request, rng, market_fare,
                        path=double_hop, stops=2, index=len(offers),
                    )
                )

        offers.sort(key=lambda offer: offer.price_total)
        return offers[: request.max_results]

    # ------------------------------------------------------------------ util
    def _connecting_hubs(
        self, origin: Airport, destination: Airport, rng: Random
    ) -> list[Airport]:
        """Hubs one airline serves on both legs, filtered to sane geometry.

        Requiring a single operator is not just cosmetic: a hidden-city fare has
        to be one ticket, and an itinerary stitched from two carriers with no
        interline agreement would not be sold as one.
        """
        ac_km = haversine_km(origin.lat, origin.lon, destination.lat, destination.lon)
        scored: list[tuple[float, Airport]] = []

        for code in one_stop_hubs(origin.iata, destination.iata):
            hub = get_airport(code)
            if hub is None or hub.hub_tier < 1:
                continue
            if hub.metro and hub.metro in {origin.metro, destination.metro}:
                continue

            ab = haversine_km(origin.lat, origin.lon, hub.lat, hub.lon)
            bc = haversine_km(hub.lat, hub.lon, destination.lat, destination.lon)
            if ab < 150 or bc < 150:
                continue
            ratio = detour_ratio(ab, bc, ac_km)
            if ratio > 1.55:
                continue
            if common_operator([(origin.iata, hub.iata), (hub.iata, destination.iata)]) is None:
                continue

            # Prefer bigger hubs and straighter routings, with a little jitter
            # so different queries don't always surface the same carrier.
            scored.append((ratio - 0.06 * hub.hub_tier + rng.uniform(0, 0.08), hub))

        scored.sort(key=lambda item: item[0])
        return [hub for _, hub in scored[:4]]

    @staticmethod
    def _carrier_for_path(path: tuple[Airport, ...], rng: Random) -> str:
        """An airline that actually flies every leg of this routing.

        Connecting paths are pre-filtered to ones a single carrier operates, so
        the fallbacks below only ever apply to a nonstop whose operators are all
        defunct and were dropped from the dataset.
        """
        legs = [(path[i].iata, path[i + 1].iata) for i in range(len(path) - 1)]

        shared = common_operator(legs)
        if shared:
            return shared

        first_leg = route_operators(*legs[0])
        if first_leg:
            return rng.choice(list(first_leg))

        anchor = path[0]
        if anchor.top_carriers:
            weights = [4, 2, 1, 1, 1, 1][: len(anchor.top_carriers)]
            return rng.choices(list(anchor.top_carriers), weights=weights, k=1)[0]

        return DEFAULT_CARRIER

    def _build_offer(
        self,
        request: SearchRequest,
        rng: Random,
        market_fare: float,
        *,
        path: tuple[Airport, ...],
        stops: int,
        index: int,
    ) -> Offer:
        carrier = self._carrier_for_path(path, rng)

        price = market_fare
        price *= STOP_MULTIPLIER.get(stops, 0.88)
        price *= CARRIER_MULTIPLIER.get(carrier, 1.0)
        price *= rng.uniform(0.93, 1.09)  # fare-bucket jitter
        price = round(max(price, 24.0) * request.adults, 2)

        depart_at = datetime.combine(
            request.departure_date,
            time(hour=rng.randrange(1, 22), minute=rng.choice((0, 5, 15, 25, 35, 45, 55))),
        )

        segments: list[Segment] = []
        cursor = depart_at
        for leg_index in range(len(path) - 1):
            leg_from, leg_to = path[leg_index], path[leg_index + 1]
            leg_km = haversine_km(leg_from.lat, leg_from.lon, leg_to.lat, leg_to.lon)
            block = _flight_minutes(leg_km)
            arrival = cursor + timedelta(minutes=block)
            segments.append(
                Segment(
                    origin=leg_from.iata,
                    destination=leg_to.iata,
                    departure_at=cursor,
                    arrival_at=arrival,
                    carrier=carrier,
                    flight_number=str(rng.randrange(100, 1999)),
                    duration_minutes=block,
                    aircraft=rng.choice(AIRCRAFT_POOL),
                    cabin=request.cabin,
                )
            )
            if leg_index < len(path) - 2:
                cursor = arrival + timedelta(
                    minutes=rng.choice((55, 70, 95, 130, 185, 240, 340))
                )

        total_minutes = int(
            (segments[-1].arrival_at - segments[0].departure_at).total_seconds() // 60
        )

        return Offer(
            provider=self.name,
            offer_id=f"MOCK-{request.origin}{request.destination}-{request.departure_date:%m%d}-{index}",
            search_origin=request.origin,
            search_destination=request.destination,
            departure_date=request.departure_date,
            price_total=price,
            currency=request.currency,
            itineraries=(Itinerary(segments=tuple(segments), duration_minutes=total_minutes),),
            validating_carriers=(carrier,),
            cabin=request.cabin,
            bookable_seats=rng.randrange(1, 9),
        )

    async def aclose(self) -> None:  # pragma: no cover - nothing to release
        return None
