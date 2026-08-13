"""Price-trend and findings history endpoints.

Every search writes price observations as a side effect, so these read back
whatever the app has already learned about a market -- no extra API spend.
"""

from __future__ import annotations

import statistics
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.db.models import HiddenCityFinding, PriceObservation
from app.schemas.search import TrendOut, TrendPointOut

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("", response_model=TrendOut)
async def price_trend(
    session: SessionDep,
    origin: str = Query(min_length=3, max_length=3),
    destination: str = Query(min_length=3, max_length=3),
    departure_date: date | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365, description="Look-back window"),
) -> TrendOut:
    """How the cheapest fare on one market has moved over time."""
    since = datetime.now(UTC) - timedelta(days=days)
    statement = (
        select(PriceObservation)
        .where(PriceObservation.origin == origin.upper())
        .where(PriceObservation.destination == destination.upper())
        .where(PriceObservation.observed_at >= since)
        .order_by(PriceObservation.observed_at.asc())
    )
    if departure_date is not None:
        statement = statement.where(PriceObservation.departure_date == departure_date)

    rows = (await session.execute(statement)).scalars().all()
    points = [
        TrendPointOut(
            observed_at=row.observed_at.isoformat(),
            min_price=round(row.min_price, 2),
            median_price=None if row.median_price is None else round(row.median_price, 2),
            offer_count=row.offer_count,
        )
        for row in rows
    ]
    prices = [row.min_price for row in rows]

    change_percent = None
    if len(prices) >= 2 and prices[0]:
        change_percent = round((prices[-1] - prices[0]) / prices[0] * 100, 1)

    return TrendOut(
        origin=origin.upper(),
        destination=destination.upper(),
        currency=rows[0].currency if rows else "USD",
        points=points,
        latest=round(prices[-1], 2) if prices else None,
        lowest=round(min(prices), 2) if prices else None,
        highest=round(max(prices), 2) if prices else None,
        average=round(statistics.fmean(prices), 2) if prices else None,
        change_percent=change_percent,
    )


@router.get("/findings")
async def recent_findings(
    session: SessionDep,
    origin: str | None = Query(default=None, min_length=3, max_length=3),
    destination: str | None = Query(
        default=None, min_length=3, max_length=3, description="Desired city B"
    ),
    min_confidence: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Best hidden-city opportunities this instance has recorded."""
    statement = (
        select(HiddenCityFinding)
        .where(HiddenCityFinding.confidence >= min_confidence)
        .order_by(HiddenCityFinding.savings.desc())
        .limit(limit)
    )
    if origin:
        statement = statement.where(HiddenCityFinding.origin == origin.upper())
    if destination:
        statement = statement.where(HiddenCityFinding.deplane_iata == destination.upper())

    rows = (await session.execute(statement)).scalars().all()
    return {
        "count": len(rows),
        "findings": [
            {
                "origin": row.origin,
                "deplane_iata": row.deplane_iata,
                "ticketed_iata": row.ticketed_iata,
                "departure_date": row.departure_date.isoformat(),
                "price": round(row.price, 2),
                "baseline_price": round(row.baseline_price, 2),
                "savings": round(row.savings, 2),
                "savings_percent": round(row.savings_percent, 1),
                "currency": row.currency,
                "carrier": row.carrier,
                "confidence": row.confidence,
                "found_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/routes")
async def learned_routes(
    session: SessionDep,
    hub: str | None = Query(default=None, min_length=3, max_length=3),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict:
    """The learned route graph: which B->C edges keep producing savings."""
    from app.db.models import RouteCandidate

    statement = (
        select(RouteCandidate)
        .where(RouteCandidate.times_probed > 0)
        .order_by(RouteCandidate.score.desc(), RouteCandidate.times_anomalous.desc())
        .limit(limit)
    )
    if hub:
        statement = statement.where(RouteCandidate.hub_iata == hub.upper())

    rows = (await session.execute(statement)).scalars().all()
    return {
        "count": len(rows),
        "routes": [
            {
                "hub_iata": row.hub_iata,
                "onward_iata": row.onward_iata,
                "source": row.source,
                "score": round(row.score, 3),
                "times_probed": row.times_probed,
                "times_anomalous": row.times_anomalous,
                "hit_rate": round(row.hit_rate, 3),
                "best_savings": None if row.best_savings is None else round(row.best_savings, 2),
                "last_probed_at": (
                    row.last_probed_at.isoformat() if row.last_probed_at else None
                ),
            }
            for row in rows
        ],
    }


@router.get("/summary")
async def summary(session: SessionDep) -> dict:
    """Headline counters for the dashboard."""
    searches = await session.scalar(
        select(func.count()).select_from(
            select(HiddenCityFinding.search_id).distinct().subquery()
        )
    )
    findings = await session.scalar(select(func.count(HiddenCityFinding.id)))
    best = await session.scalar(select(func.max(HiddenCityFinding.savings)))
    average = await session.scalar(select(func.avg(HiddenCityFinding.savings)))
    observations = await session.scalar(select(func.count(PriceObservation.id)))

    if searches is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Summary unavailable")

    return {
        "searches_with_findings": int(searches or 0),
        "total_findings": int(findings or 0),
        "best_savings": None if best is None else round(float(best), 2),
        "average_savings": None if average is None else round(float(average), 2),
        "price_observations": int(observations or 0),
    }
