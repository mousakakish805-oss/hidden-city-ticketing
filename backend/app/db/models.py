"""ORM models: route cache, offer cache, price history and findings.

Everything is portable between PostgreSQL and SQLite; JSON payloads upgrade to
``JSONB`` automatically when running on Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

JSONColumn = JSON().with_variant(JSONB, "postgresql")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class RouteCandidate(Base, TimestampMixin):
    """A learned or seeded "C is reachable through B" edge.

    ``times_probed`` / ``times_anomalous`` turn the batch engine into a system
    that gets cheaper and better-targeted the more it is used: edges that keep
    producing savings float to the top of the probe order.
    """

    __tablename__ = "route_candidates"
    __table_args__ = (
        UniqueConstraint("hub_iata", "onward_iata", name="uq_route_candidate_edge"),
        Index("ix_route_candidate_hub_score", "hub_iata", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hub_iata: Mapped[str] = mapped_column(String(4), index=True, nullable=False)
    onward_iata: Mapped[str] = mapped_column(String(4), index=True, nullable=False)
    # "seed" | "geometric" | "learned"
    source: Mapped[str] = mapped_column(String(16), default="seed", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    times_probed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    times_anomalous: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Probes that succeeded but found no flights at all. A market that keeps
    # coming back empty has stopped being served, whatever the reason -- this
    # is how the app corrects a route dataset that has gone stale.
    times_empty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_savings: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_probed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def hit_rate(self) -> float:
        # Tolerates an unflushed row, whose column defaults have not applied yet.
        if not self.times_probed:
            return 0.0
        return (self.times_anomalous or 0) / self.times_probed

    @property
    def empty_rate(self) -> float:
        if not self.times_probed:
            return 0.0
        return (self.times_empty or 0) / self.times_probed


class OfferCache(Base, TimestampMixin):
    """Raw normalised provider results for one (origin, destination, date) leg.

    Lets a batch run reuse probes fired by an earlier search and keeps us well
    inside provider quotas.
    """

    __tablename__ = "offer_cache"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "origin",
            "destination",
            "departure_date",
            "cabin",
            "adults",
            # Prices in two currencies are two different results, not one
            # result with a label -- see OfferCacheRepository._row_for.
            "currency",
            name="uq_offer_cache_key",
        ),
        Index("ix_offer_cache_fetched", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    origin: Mapped[str] = mapped_column(String(4), nullable=False)
    destination: Mapped[str] = mapped_column(String(4), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    cabin: Mapped[str] = mapped_column(String(24), default="ECONOMY", nullable=False)
    adults: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    offer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONColumn, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SearchQuery(Base, TimestampMixin):
    """One user-initiated hidden-city search and its batch-run state."""

    __tablename__ = "search_queries"
    __table_args__ = (
        Index("ix_search_query_route", "origin", "destination", "departure_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    origin: Mapped[str] = mapped_column(String(4), nullable=False)
    destination: Mapped[str] = mapped_column(String(4), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Set for a return trip. The two directions are still priced as two
    # separate one-way tickets -- see SearchService._execute.
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    adults: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cabin: Mapped[str] = mapped_column(String(24), default="ECONOMY", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)

    # pending | running | complete | failed
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    # Two columns because there are two audiences. ``error`` is the exception
    # type and vendor text, kept for whoever operates this; ``user_error`` is
    # the translated, plain-language version that is safe to put in a browser.
    # See services/errors.py.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    baseline_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_hidden_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_savings: Mapped[float | None] = mapped_column(Float, nullable=True)

    candidates_planned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_probed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Fully rendered API response, so a completed search replays instantly.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    findings: Mapped[list[HiddenCityFinding]] = relationship(
        back_populates="search", cascade="all, delete-orphan", lazy="selectin"
    )


class HiddenCityFinding(Base, TimestampMixin):
    """A confirmed price anomaly: A->C via B priced below A->B."""

    __tablename__ = "hidden_city_findings"
    __table_args__ = (
        Index("ix_finding_route", "origin", "deplane_iata", "departure_date"),
        Index("ix_finding_savings", "savings"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    search_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("search_queries.id", ondelete="CASCADE"), nullable=False
    )

    origin: Mapped[str] = mapped_column(String(4), nullable=False)
    deplane_iata: Mapped[str] = mapped_column(String(4), nullable=False)      # B
    ticketed_iata: Mapped[str] = mapped_column(String(4), nullable=False)     # C
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)

    price: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_price: Mapped[float] = mapped_column(Float, nullable=False)
    savings: Mapped[float] = mapped_column(Float, nullable=False)
    savings_percent: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    carrier: Mapped[str] = mapped_column(String(8), nullable=False)
    deplane_segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    segments_before_target: Mapped[int] = mapped_column(Integer, nullable=False)
    layover_minutes_at_target: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_flags: Mapped[list[str]] = mapped_column(JSONColumn, default=list, nullable=False)
    itinerary: Mapped[dict[str, Any]] = mapped_column(JSONColumn, nullable=False)

    search: Mapped[SearchQuery] = relationship(back_populates="findings")


class PriceObservation(Base):
    """Time series of the cheapest fare seen on a market. Powers trend charts."""

    __tablename__ = "price_observations"
    __table_args__ = (
        Index("ix_price_obs_market", "origin", "destination", "departure_date", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(4), nullable=False)
    destination: Mapped[str] = mapped_column(String(4), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    min_price: Mapped[float] = mapped_column(Float, nullable=False)
    median_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    offer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class DisclaimerAcknowledgement(Base):
    """Audit trail proving the operational-risk warning was shown and accepted."""

    __tablename__ = "disclaimer_acknowledgements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_token: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    search_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
