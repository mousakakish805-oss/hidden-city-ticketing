"""Candidate generation: given A and B, which onward cities C should we probe?

Three sources, merged and ranked best-first:

1. **Route graph** -- destinations with real nonstop service from B, straight
   out of the global dataset. This is the primary source and it works for any
   hub on earth, not just ones somebody remembered to list.
2. **Learned** -- edges that previously produced real anomalies, from Postgres.
   The system gets better at guessing the more it is used.
3. **Geometric** -- a fallback for airports the route snapshot does not cover,
   asking only whether B sits on the great circle from A to C.

Every probe costs an upstream API call, so ranking quality is what determines
how much this feature costs to run.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.geo import detour_ratio, haversine_km
from app.data.airports import Airport, all_airports, get_airport
from app.data.routes import has_route, onward_markets
from app.data.service_status import suspended_codes
from app.db.models import RouteCandidate
from app.i18n import DEFAULT_LANGUAGE, translate

SOURCE_BONUS: dict[str, float] = {"learned": 2.0, "route": 1.8, "geometric": 0.0}

# Only consider geometric candidates at airports with real scheduled service;
# without it we would burn API calls on airstrips.
MIN_GEOMETRIC_HUB_TIER = 1

# A market needs enough service for through-fares to exist at all. Below this,
# a probe is very unlikely to return anything and the API call is wasted.
MIN_CANDIDATE_DESTINATIONS = 6

# Destinations served at which a market counts as fully "viable" to probe.
VIABILITY_SATURATION = 60

# Fares grow sublinearly with distance; this is the exponent used to predict
# whether a further destination can still be cheaper. Matches the curve in the
# mock pricing model, and is roughly what real published fares follow.
DISTANCE_EXPONENT = 0.95

# An expected-fare ratio at or below this is worth probing; the window sets how
# sharply the score falls off above it.
RATIO_CEILING = 1.15
RATIO_WINDOW = 0.35

# How much evidence before a market is retired as unserved. Deliberately not
# one bad probe: a single empty response can be a sold-out date, not a dead
# route.
DEAD_MARKET_MIN_PROBES = 3
DEAD_MARKET_EMPTY_RATE = 0.9


@dataclass(frozen=True, slots=True)
class CandidateRoute:
    """A prospective ticketed destination C for the extended A->C query."""

    iata: str
    city: str
    country: str
    source: str
    score: float
    detour_ratio: float
    onward_km: float
    total_km: float
    served_nonstop: bool
    reason_key: str
    reason_params: dict[str, Any] = field(default_factory=dict)

    def reason(self, lang: str = DEFAULT_LANGUAGE) -> str:
        return translate(self.reason_key, lang, **self.reason_params)

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
        return {
            "iata": self.iata,
            "city": self.city,
            "country": self.country,
            "source": self.source,
            "score": round(self.score, 3),
            "detour_ratio": round(self.detour_ratio, 3),
            "onward_km": round(self.onward_km),
            "total_km": round(self.total_km),
            "served_nonstop": self.served_nonstop,
            "reason": self.reason(lang),
        }


def _excluded_codes(origin: Airport, target: Airport) -> set[str]:
    """Airports that can never be a valid C: the endpoints and their metro twins."""
    excluded = {origin.iata, target.iata}
    for airport in all_airports():
        if airport.metro and airport.metro in {origin.metro, target.metro}:
            excluded.add(airport.iata)
    return excluded


def _evaluate(
    origin: Airport,
    target: Airport,
    candidate: Airport,
    origin_target_km: float,
    source: str,
    learned_bonus: float = 0.0,
) -> CandidateRoute | None:
    """Score one candidate, or reject it as geometrically implausible."""
    onward_km = haversine_km(target.lat, target.lon, candidate.lat, candidate.lon)
    if not (settings.min_onward_leg_km <= onward_km <= settings.max_onward_leg_km):
        return None

    total_km = haversine_km(origin.lat, origin.lon, candidate.lat, candidate.lon)
    # C must genuinely lie *beyond* B, otherwise B is not a stop on the way.
    if total_km <= origin_target_km:
        return None

    ratio = detour_ratio(origin_target_km, onward_km, total_km)
    if ratio > settings.max_detour_ratio:
        return None

    # A market with almost no service cannot produce a through-fare, however
    # cheap it looks. Learned edges have already proven themselves, so they
    # bypass this floor.
    if source != "learned" and candidate.destination_count < MIN_CANDIDATE_DESTINATIONS:
        return None

    # The core signal: predict what A->C should cost relative to A->B.
    #
    # Published fares track distance sublinearly and scale with how expensive
    # the destination market is, so a ratio below 1 says C is cheaper to reach
    # than B *despite being further* -- which is precisely a hidden-city
    # opportunity. Modelling it directly beats the proxies it replaces: a large
    # but distant airport (Hannover behind Istanbul) correctly scores badly,
    # because the extra distance outweighs its lower demand.
    expected_ratio = (
        (total_km**DISTANCE_EXPONENT) * candidate.demand_index
    ) / ((origin_target_km**DISTANCE_EXPONENT) * target.demand_index)
    anomaly_signal = min(max((RATIO_CEILING - expected_ratio) / RATIO_WINDOW, 0.0), 1.0)

    straightness = (settings.max_detour_ratio - ratio) / (settings.max_detour_ratio - 1.0)

    # How real the market is. Without this, a cheap airstrip outranks Skopje.
    viability = min(
        1.0,
        math.log(candidate.destination_count + 1) / math.log(VIABILITY_SATURATION),
    )
    served_nonstop = has_route(target.iata, candidate.iata)

    score = (
        4.0 * anomaly_signal
        + 1.5 * max(straightness, 0.0)
        + 1.5 * viability
        + SOURCE_BONUS.get(source, 0.0)
        + learned_bonus
    )

    # Stored as a key plus params so the API can render it in any language.
    if source == "learned":
        reason_key, reason_params = "candidate.learned", {"target": target.iata}
    elif expected_ratio < 0.95:
        reason_key = "candidate.cheaper_market"
        reason_params = {"city": candidate.city, "target_city": target.city}
    elif served_nonstop:
        reason_key = "candidate.nonstop"
        reason_params = {"target": target.iata, "city": candidate.city}
    else:
        reason_key = "candidate.on_the_line"
        reason_params = {
            "target": target.iata,
            "origin_city": origin.city,
            "city": candidate.city,
        }

    return CandidateRoute(
        iata=candidate.iata,
        city=candidate.city,
        country=candidate.country,
        source=source,
        score=score,
        detour_ratio=ratio,
        onward_km=onward_km,
        total_km=total_km,
        served_nonstop=served_nonstop,
        reason_key=reason_key,
        reason_params=reason_params,
    )


def rank_candidates(
    origin_iata: str,
    target_iata: str,
    *,
    limit: int | None = None,
    learned: Mapping[str, float] | None = None,
    dead_markets: Collection[str] | None = None,
) -> list[CandidateRoute]:
    """Pure, synchronous ranking. The async wrapper adds DB-learned edges."""
    origin = get_airport(origin_iata)
    target = get_airport(target_iata)
    if origin is None or target is None:
        return []

    limit = limit or settings.max_candidate_destinations
    learned = learned or {}
    excluded = _excluded_codes(origin, target)
    # Airports that have stopped flying: curated for the cold start, learned
    # from empty responses thereafter.
    excluded |= suspended_codes()
    if dead_markets:
        excluded |= {code.upper() for code in dead_markets}
    origin_target_km = haversine_km(origin.lat, origin.lon, target.lat, target.lon)

    # Best source wins per airport: learned > route graph > geometry.
    sources: dict[str, str] = {}
    for code in onward_markets(target.iata):
        sources[code] = "route"
    for code in learned:
        sources[code] = "learned"
    for airport in all_airports():
        if airport.hub_tier >= MIN_GEOMETRIC_HUB_TIER:
            sources.setdefault(airport.iata, "geometric")

    results: list[CandidateRoute] = []
    for code, source in sources.items():
        if code in excluded:
            continue
        candidate = get_airport(code)
        if candidate is None:
            continue
        evaluated = _evaluate(
            origin,
            target,
            candidate,
            origin_target_km,
            source,
            learned_bonus=learned.get(code, 0.0),
        )
        if evaluated is not None:
            results.append(evaluated)

    results.sort(key=lambda item: (-item.score, item.detour_ratio, item.iata))
    return results[:limit]


async def load_learned_edges(session: AsyncSession, target_iata: str) -> dict[str, float]:
    """Bonus weights for onward markets that have paid off before at this hub."""
    statement = (
        select(RouteCandidate)
        .where(RouteCandidate.hub_iata == target_iata.upper())
        .where(RouteCandidate.times_anomalous > 0)
        .order_by(RouteCandidate.score.desc())
        .limit(40)
    )
    rows = (await session.execute(statement)).scalars().all()
    # Cap the bonus so history informs the ranking without freezing it.
    return {row.onward_iata: min(row.hit_rate * 2.0, 2.0) for row in rows}


async def generate_candidates(
    session: AsyncSession | None,
    origin_iata: str,
    target_iata: str,
    *,
    limit: int | None = None,
) -> list[CandidateRoute]:
    """Full candidate generation, including anything learned from past runs."""
    learned: dict[str, float] = {}
    dead: set[str] = set()
    if session is not None:
        learned = await load_learned_edges(session, target_iata)
        dead = await load_dead_markets(session, target_iata)
    return rank_candidates(
        origin_iata, target_iata, limit=limit, learned=learned, dead_markets=dead
    )


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    """What one probe taught us about an onward market."""

    onward_iata: str
    produced_anomaly: bool
    savings: float | None
    offer_count: int

    @property
    def was_empty(self) -> bool:
        """Succeeded upstream but returned nothing -- the market is not served."""
        return self.offer_count == 0


async def record_probe_outcomes(
    session: AsyncSession,
    target_iata: str,
    outcomes: Iterable[ProbeOutcome],
) -> None:
    """Persist what each probe taught us, so future runs probe smarter."""
    hub = target_iata.upper()
    outcome_list = list(outcomes)
    if not outcome_list:
        return

    codes = [outcome.onward_iata for outcome in outcome_list]
    existing = {
        row.onward_iata: row
        for row in (
            await session.execute(
                select(RouteCandidate)
                .where(RouteCandidate.hub_iata == hub)
                .where(RouteCandidate.onward_iata.in_(codes))
            )
        ).scalars()
    }

    now = datetime.now(UTC)
    for outcome in outcome_list:
        row = existing.get(outcome.onward_iata)
        if row is None:
            # Counters are set explicitly: SQLAlchemy column defaults are only
            # applied at flush time, and we increment before flushing.
            row = RouteCandidate(
                hub_iata=hub,
                onward_iata=outcome.onward_iata,
                source="learned",
                score=0.0,
                times_probed=0,
                times_anomalous=0,
                times_empty=0,
            )
            session.add(row)
            existing[outcome.onward_iata] = row

        row.times_probed += 1
        if outcome.was_empty:
            row.times_empty += 1
        if outcome.produced_anomaly:
            row.times_anomalous += 1
            if outcome.savings is not None:
                row.best_savings = max(row.best_savings or 0.0, outcome.savings)
        row.last_probed_at = now
        # Hit rate scaled by a confidence factor that grows with sample size.
        row.score = row.hit_rate * min(row.times_probed / 5.0, 1.0)

    await session.flush()


async def load_dead_markets(session: AsyncSession, target_iata: str) -> set[str]:
    """Onward markets that keep coming back empty, so are not worth probing.

    This is what keeps a stale route dataset from wasting API calls forever:
    whatever the reason a market stopped being served, enough empty responses
    retire it without anyone maintaining a list.
    """
    statement = (
        select(RouteCandidate)
        .where(RouteCandidate.hub_iata == target_iata.upper())
        .where(RouteCandidate.times_probed >= DEAD_MARKET_MIN_PROBES)
        .where(RouteCandidate.times_anomalous == 0)
    )
    rows = (await session.execute(statement)).scalars().all()
    return {row.onward_iata for row in rows if row.empty_rate >= DEAD_MARKET_EMPTY_RATE}
