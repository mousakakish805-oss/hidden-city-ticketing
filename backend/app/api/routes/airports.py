"""Airport lookup for the smart search inputs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.hub_graph import generate_candidates
from app.data.airports import Airport, get_airport, search_airports
from app.schemas.search import AirportOut

router = APIRouter(prefix="/airports", tags=["airports"])


def _to_out(airport: Airport) -> AirportOut:
    return AirportOut(
        iata=airport.iata,
        name=airport.name,
        city=airport.city,
        country=airport.country,
        country_code=airport.country_code,
        region=airport.region,
        lat=airport.lat,
        lon=airport.lon,
        hub_tier=airport.hub_tier,
        destination_count=airport.destination_count,
        carrier_count=airport.carrier_count,
        label=airport.label,
    )


@router.get("", response_model=list[AirportOut])
async def list_airports(
    q: str = Query(default="", description="IATA code, city, airport or country fragment"),
    limit: int = Query(default=10, ge=1, le=50),
    country: str | None = Query(
        default=None, description="Restrict to one country name or ISO alpha-2 code"
    ),
    scheduled_only: bool = Query(
        default=True,
        description="Only airports with known scheduled service. Turn off to reach every "
        "IATA-coded field in the dataset.",
    ),
) -> list[AirportOut]:
    """Autocomplete over every IATA airport worldwide.

    Empty ``q`` returns the busiest hubs, which is the most useful default when
    ~6,000 airports are in scope.
    """
    return [
        _to_out(airport)
        for airport in search_airports(
            q, limit=limit, country=country, scheduled_only=scheduled_only
        )
    ]


@router.get("/{iata}", response_model=AirportOut)
async def get_one(iata: str) -> AirportOut:
    airport = get_airport(iata)
    if airport is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown airport '{iata}'")
    return _to_out(airport)


@router.get("/{iata}/candidates")
async def preview_candidates(
    iata: str,
    origin: str = Query(description="Origin airport the route would start from"),
    limit: int = Query(default=12, ge=1, le=40),
) -> dict:
    """Which onward cities C the batch engine would probe for this A/B pair.

    Exposed for transparency and tuning -- it runs the ranking without spending
    a single upstream API call.
    """
    if get_airport(iata) is None or get_airport(origin) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown airport code")

    candidates = await generate_candidates(None, origin, iata, limit=limit)
    return {
        "origin": origin.upper(),
        "target": iata.upper(),
        "count": len(candidates),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
