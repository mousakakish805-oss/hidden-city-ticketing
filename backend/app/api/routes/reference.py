"""Reference data endpoints: airlines, countries and dataset coverage.

Backed entirely by the generated dataset, so these are cheap, offline lookups
that never touch a flight provider.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.data.airlines import Airline, all_airlines, get_airline, search_airlines
from app.data.airports import all_airports
from app.data.countries import all_countries, all_regions, get_country, search_countries
from app.data.routes import route_count
from app.schemas.search import AirlineOut, CountryOut

router = APIRouter(tags=["reference"])


def _to_airline_out(airline: Airline) -> AirlineOut:
    return AirlineOut(
        iata=airline.iata,
        name=airline.name,
        country=airline.country,
        active=airline.active,
        icao=airline.icao,
        booking_url=airline.booking_url,
        label=airline.label,
    )


@router.get("/airlines", response_model=list[AirlineOut])
async def list_airlines(
    q: str = Query(default="", description="IATA code, airline name or country"),
    limit: int = Query(default=20, ge=1, le=200),
    active_only: bool = Query(default=True, description="Exclude defunct carriers"),
) -> list[AirlineOut]:
    return [
        _to_airline_out(airline)
        for airline in search_airlines(q, limit=limit, active_only=active_only)
    ]


@router.get("/airlines/{iata}", response_model=AirlineOut)
async def get_one_airline(iata: str) -> AirlineOut:
    airline = get_airline(iata)
    if airline is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown airline '{iata}'")
    return _to_airline_out(airline)


@router.get("/countries", response_model=list[CountryOut])
async def list_countries(
    q: str = Query(default="", description="Country name or ISO alpha-2 code"),
    limit: int = Query(default=250, ge=1, le=300),
) -> list[CountryOut]:
    return [
        CountryOut(
            name=country.name,
            code=country.code,
            region=country.region,
            airport_count=country.airport_count,
        )
        for country in search_countries(q, limit=limit)
    ]


@router.get("/countries/{code}", response_model=CountryOut)
async def get_one_country(code: str) -> CountryOut:
    country = get_country(code)
    if country is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown country '{code}'")
    return CountryOut(
        name=country.name,
        code=country.code,
        region=country.region,
        airport_count=country.airport_count,
    )


@router.get("/regions")
async def list_regions() -> dict:
    return {"regions": list(all_regions())}


@router.get("/coverage")
async def coverage() -> dict:
    """What the bundled reference dataset actually contains."""
    airports = all_airports()
    scheduled = [airport for airport in airports if airport.is_scheduled]
    return {
        "airports": len(airports),
        "airports_with_scheduled_service": len(scheduled),
        "airlines": len(all_airlines()),
        "active_airlines": sum(1 for airline in all_airlines() if airline.active),
        "countries": len(all_countries()),
        "regions": len(all_regions()),
        "directed_routes": sum(route_count(airport.iata) for airport in airports),
        "hub_tiers": {
            str(tier): sum(1 for airport in airports if airport.hub_tier == tier)
            for tier in (3, 2, 1, 0)
        },
        "source": "OpenFlights (Open Database License)",
    }
