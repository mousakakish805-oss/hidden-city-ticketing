"""Global airline reference data (~1,100 IATA-coded carriers).

Providers return two-letter carrier codes; this turns "TK" into "Turkish
Airlines" everywhere it is shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.data._store import load
from app.data.airline_sites import booking_site


@dataclass(frozen=True, slots=True)
class Airline:
    iata: str
    name: str
    country: str
    active: bool
    icao: str | None = None
    alias: str | None = None
    callsign: str | None = None
    booking_url: str | None = None

    @property
    def label(self) -> str:
        return f"{self.iata} - {self.name}"


@lru_cache(maxsize=1)
def _airlines() -> tuple[Airline, ...]:
    return tuple(
        Airline(
            iata=row["iata"],
            name=row["name"],
            country=row.get("country", ""),
            active=bool(row.get("active")),
            icao=row.get("icao"),
            alias=row.get("alias"),
            callsign=row.get("callsign"),
            # Merged at load time, not build time, so corrections to the
            # curated site list do not require regenerating the dataset.
            booking_url=booking_site(row["iata"]),
        )
        for row in load("airlines")
    )


@lru_cache(maxsize=1)
def airline_index() -> dict[str, Airline]:
    return {airline.iata: airline for airline in _airlines()}


def all_airlines() -> tuple[Airline, ...]:
    return _airlines()


def get_airline(iata: str) -> Airline | None:
    return airline_index().get(iata.strip().upper())


def airline_name(iata: str | None) -> str:
    """Human-readable carrier name, falling back to the raw code."""
    if not iata:
        return "Unknown"
    airline = get_airline(iata)
    return airline.name if airline else iata.upper()


def airline_booking_url(iata: str | None) -> str | None:
    """Official site to book on, or ``None`` if we have no verified URL."""
    if not iata:
        return None
    airline = get_airline(iata)
    return airline.booking_url if airline else booking_site(iata)


def search_airlines(query: str, limit: int = 10, *, active_only: bool = True) -> list[Airline]:
    text = query.strip().casefold()
    pool = [a for a in _airlines() if a.active or not active_only]

    if not text:
        return sorted(pool, key=lambda a: a.name)[:limit]

    scored: list[tuple[int, str, Airline]] = []
    for airline in pool:
        code = airline.iata.casefold()
        name = airline.name.casefold()
        if code == text:
            rank = 0
        elif name.startswith(text):
            rank = 1
        elif text in name:
            rank = 2
        elif text in airline.country.casefold():
            rank = 3
        else:
            continue
        scored.append((rank, airline.name, airline))

    scored.sort(key=lambda item: item[:2])
    return [item[2] for item in scored[:limit]]
