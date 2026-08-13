"""Global airport reference data.

Every IATA-coded airport worldwide (~6,000 across 235 countries), loaded from
the generated dataset. See ``scripts/build_reference_data.py`` for how the
derived fields are computed.

``hub_tier`` comes from how many distinct destinations an airport serves:
    3 = intercontinental hub (150+ destinations)
    2 = major hub (60+)
    1 = regional airport (12+)
    0 = thin or unscheduled

``demand_index`` is a relative fare-pressure proxy combining size with carrier
dominance. A big airport controlled by one airline (IST at 1.25) is expensive
to fly *to*; a thin market behind it (SKP at 0.88) is not. That gap is the
whole basis of hidden-city pricing.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.data._store import load


@dataclass(frozen=True, slots=True)
class Airport:
    iata: str
    name: str
    city: str
    country: str
    country_code: str | None
    region: str
    lat: float
    lon: float
    hub_tier: int
    demand_index: float
    metro: str | None
    destination_count: int
    carrier_count: int
    concentration: float
    top_carriers: tuple[str, ...] = ()
    icao: str | None = None
    tz: str | None = None

    @property
    def label(self) -> str:
        return f"{self.iata} - {self.city}, {self.country}"

    @property
    def is_scheduled(self) -> bool:
        """Whether the airport has any known scheduled service."""
        return self.destination_count > 0


@lru_cache(maxsize=1)
def _airports() -> tuple[Airport, ...]:
    return tuple(
        Airport(
            iata=row["iata"],
            name=row["name"],
            city=row["city"],
            country=row["country"],
            country_code=row.get("country_code"),
            region=row.get("region", "Other"),
            lat=row["lat"],
            lon=row["lon"],
            hub_tier=row["hub_tier"],
            demand_index=row["demand_index"],
            metro=row.get("metro"),
            destination_count=row.get("destination_count", 0),
            carrier_count=row.get("carrier_count", 0),
            concentration=row.get("concentration", 0.0),
            top_carriers=tuple(row.get("top_carriers") or ()),
            icao=row.get("icao"),
            tz=row.get("tz"),
        )
        for row in load("airports")
    )


@lru_cache(maxsize=1)
def airport_index() -> dict[str, Airport]:
    return {airport.iata: airport for airport in _airports()}


@lru_cache(maxsize=1)
def metro_index() -> dict[str, tuple[str, ...]]:
    """Metro code -> every IATA code serving that city, e.g. IST -> (IST, SAW)."""
    groups: dict[str, list[str]] = {}
    for airport in _airports():
        if airport.metro:
            groups.setdefault(airport.metro, []).append(airport.iata)
    return {metro: tuple(codes) for metro, codes in groups.items()}


@lru_cache(maxsize=1)
def _search_corpus() -> tuple[tuple[str, str, str, str, Airport], ...]:
    """Pre-lowercased fields so autocomplete does not re-case 6,000 rows a keystroke."""
    return tuple(
        (
            airport.iata.lower(),
            airport.city.casefold(),
            airport.name.casefold(),
            airport.country.casefold(),
            airport,
        )
        for airport in _airports()
    )


def all_airports() -> tuple[Airport, ...]:
    return _airports()


def get_airport(iata: str) -> Airport | None:
    return airport_index().get(iata.strip().upper())


def require_airport(iata: str) -> Airport:
    airport = get_airport(iata)
    if airport is None:
        raise KeyError(f"Unknown airport code: {iata!r}")
    return airport


def sibling_airports(iata: str) -> tuple[str, ...]:
    """Other airports serving the same city, e.g. IST -> (SAW,)."""
    airport = get_airport(iata)
    if airport is None or not airport.metro:
        return ()
    return tuple(code for code in metro_index().get(airport.metro, ()) if code != airport.iata)


def search_airports(
    query: str,
    limit: int = 10,
    *,
    country: str | None = None,
    scheduled_only: bool = False,
) -> list[Airport]:
    """Rank airports for autocomplete.

    With ~6,000 airports in scope, ties are broken by how many destinations an
    airport serves -- so typing "lon" surfaces Heathrow before London, Ontario.
    """
    text = query.strip().casefold()
    country_filter = country.strip().casefold() if country else None

    def passes(airport: Airport) -> bool:
        if scheduled_only and not airport.is_scheduled:
            return False
        return not (
            country_filter
            and country_filter
            not in (airport.country.casefold(), (airport.country_code or "").casefold())
        )

    if not text:
        pool = [airport for airport in _airports() if passes(airport)]
        pool.sort(key=lambda a: (-a.destination_count, a.city))
        return pool[:limit]

    scored: list[tuple[int, int, str, Airport]] = []
    for iata, city, name, country_name, airport in _search_corpus():
        if not passes(airport):
            continue

        if iata == text:
            rank = 0
        elif city == text:
            rank = 1
        elif city.startswith(text):
            rank = 2
        elif name.startswith(text) or country_name.startswith(text):
            rank = 3
        elif text in city or text in name:
            rank = 4
        elif text in country_name or text in iata:
            rank = 5
        else:
            continue
        scored.append((rank, -airport.destination_count, airport.city, airport))

    scored.sort(key=lambda item: item[:3])
    return [item[3] for item in scored[:limit]]
