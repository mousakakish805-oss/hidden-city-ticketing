"""Offer caching and price-trend recording.

Two jobs, both backed by the same writes:

* **Cache** -- a probe fired for one user's search is reused for the next,
  which is what keeps a fan-out design affordable under provider quotas.
* **Trend history** -- every fetch also lands a row in ``price_observations``,
  turning ordinary usage into a longitudinal record of what each market costs.

All calls are sequential by design (see ``core/batch_engine``).
"""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import OfferCache, PriceObservation
from app.providers.base import Offer, SearchRequest

logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; normalise before comparing."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class OfferCacheRepository:
    def __init__(self, session: AsyncSession, provider: str) -> None:
        self._session = session
        self._provider = provider

    async def get(self, request: SearchRequest) -> list[Offer] | None:
        """Return cached offers for ``request`` if still fresh, else ``None``."""
        row = await self._row_for(request)
        if row is None:
            return None

        age = datetime.now(UTC) - _as_utc(row.fetched_at)
        if age > timedelta(seconds=settings.offer_cache_ttl_seconds):
            return None

        try:
            return [Offer.from_dict(payload) for payload in row.payload]
        except (KeyError, ValueError, TypeError):
            logger.warning("Discarding unreadable cache entry for %s", request.destination)
            return None

    async def put(self, request: SearchRequest, offers: list[Offer]) -> None:
        """Upsert the cache entry and append a price observation."""
        prices = [offer.price_total for offer in offers]
        min_price = min(prices, default=None)
        payload = [offer.to_dict() for offer in offers]

        row = await self._row_for(request)
        if row is None:
            row = OfferCache(
                provider=self._provider,
                origin=request.origin,
                destination=request.destination,
                departure_date=request.departure_date,
                cabin=request.cabin,
                adults=request.adults,
            )
            self._session.add(row)

        row.currency = request.currency
        row.offer_count = len(offers)
        row.min_price = min_price
        row.payload = payload
        row.fetched_at = datetime.now(UTC)

        if min_price is not None:
            self._session.add(
                PriceObservation(
                    origin=request.origin,
                    destination=request.destination,
                    departure_date=request.departure_date,
                    provider=self._provider,
                    currency=request.currency,
                    min_price=min_price,
                    median_price=statistics.median(prices),
                    offer_count=len(offers),
                )
            )

        await self._session.flush()

    async def _row_for(self, request: SearchRequest) -> OfferCache | None:
        statement = (
            select(OfferCache)
            .where(OfferCache.provider == self._provider)
            .where(OfferCache.origin == request.origin)
            .where(OfferCache.destination == request.destination)
            .where(OfferCache.departure_date == request.departure_date)
            .where(OfferCache.cabin == request.cabin)
            .where(OfferCache.adults == request.adults)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()
