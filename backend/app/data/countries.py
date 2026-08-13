"""Country reference data: every country that has an IATA-coded airport."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.data._store import load


@dataclass(frozen=True, slots=True)
class Country:
    name: str
    code: str | None
    region: str
    airport_count: int


@lru_cache(maxsize=1)
def _countries() -> tuple[Country, ...]:
    return tuple(
        Country(
            name=row["name"],
            code=row.get("code"),
            region=row.get("region", "Other"),
            airport_count=row.get("airport_count", 0),
        )
        for row in load("countries")
    )


def all_countries() -> tuple[Country, ...]:
    return _countries()


@lru_cache(maxsize=1)
def _by_code() -> dict[str, Country]:
    return {country.code: country for country in _countries() if country.code}


def get_country(code_or_name: str) -> Country | None:
    key = code_or_name.strip()
    if len(key) == 2:
        found = _by_code().get(key.upper())
        if found:
            return found
    folded = key.casefold()
    return next((c for c in _countries() if c.name.casefold() == folded), None)


def search_countries(query: str, limit: int = 20) -> list[Country]:
    text = query.strip().casefold()
    if not text:
        return sorted(_countries(), key=lambda c: -c.airport_count)[:limit]

    matches = [
        country
        for country in _countries()
        if country.name.casefold().startswith(text)
        or text in country.name.casefold()
        or (country.code or "").casefold() == text
    ]
    matches.sort(key=lambda c: (not c.name.casefold().startswith(text), -c.airport_count))
    return matches[:limit]


@lru_cache(maxsize=1)
def all_regions() -> tuple[str, ...]:
    return tuple(sorted({country.region for country in _countries()}))
