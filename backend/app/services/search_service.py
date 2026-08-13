"""Orchestration for one hidden-city search.

Sequence:

1. Price the **baseline** A -> B market. Without it there is nothing to compare
   against, so a failure here aborts the run.
2. Generate ranked **candidate** destinations C behind B.
3. Serve what the cache already knows, then **fan out** the rest concurrently.
4. Run the Pandas **analysis** to find A -> C itineraries stopping at B that
   undercut the baseline.
5. **Persist** findings, refresh the learned route graph, store the rendered
   result, and emit a completion event.

Database work is deliberately kept either side of the concurrent fan-out --
an ``AsyncSession`` cannot be shared across simultaneous tasks.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.analyzer import AnalysisResult, analyse
from app.core.batch_engine import BatchEngine, ProbeResult
from app.core.hub_graph import (
    CandidateRoute,
    ProbeOutcome,
    generate_candidates,
    record_probe_outcomes,
)
from app.data.airports import get_airport
from app.db.models import HiddenCityFinding, SearchQuery
from app.i18n import is_rtl, translate
from app.providers.base import FlightProvider, Offer, SearchRequest
from app.schemas.search import SearchRequestIn
from app.services.cache import OfferCacheRepository
from app.services.disclaimer import disclaimer_payload
from app.services.errors import operator_detail, user_facing_message
from app.services.events import event_bus

logger = logging.getLogger(__name__)


class SearchFailed(RuntimeError):
    """The run could not produce a comparable result."""


@dataclass(slots=True)
class LegResult:
    """One direction of a trip, priced and analysed end to end.

    A return trip is two of these -- two separate one-way tickets, never a
    round-trip fare, because a hidden-city itinerary cannot survive on one.
    """

    leg: str  # "outbound" | "inbound"
    origin: str
    destination: str
    departure_date: date
    analysis: AnalysisResult
    candidates: list[CandidateRoute]
    probe_results: list[ProbeResult]


def _airport_summary(iata: str) -> dict[str, Any]:
    airport = get_airport(iata)
    if airport is None:
        return {"iata": iata, "city": iata, "country": None}
    return {
        "iata": airport.iata,
        "city": airport.city,
        "country": airport.country,
        "name": airport.name,
    }


class SearchService:
    def __init__(self, session: AsyncSession, provider: FlightProvider) -> None:
        self._session = session
        self._provider = provider
        self._cache = OfferCacheRepository(session, provider.name)

    # ------------------------------------------------------------- lifecycle
    async def create_search(self, params: SearchRequestIn) -> SearchQuery:
        record = SearchQuery(
            origin=params.origin,
            destination=params.destination,
            departure_date=params.departure_date,
            return_date=params.return_date,
            candidates_planned=0,
            candidates_probed=0,
            adults=params.adults,
            cabin=params.cabin,
            currency=params.currency,
            provider=self._provider.name,
            status="pending",
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_search(self, search_id: str) -> SearchQuery | None:
        return (
            await self._session.execute(
                select(SearchQuery).where(SearchQuery.id == search_id)
            )
        ).scalar_one_or_none()

    # ----------------------------------------------------------------- run
    async def run(self, search_id: str, params: SearchRequestIn) -> dict[str, Any]:
        started = time.perf_counter()
        record = await self.get_search(search_id)
        if record is None:
            raise SearchFailed(f"Unknown search {search_id}")

        record.status = "running"
        await self._session.flush()
        await self._publish(search_id, {"type": "started", "query": params.model_dump(mode="json")})

        try:
            payload = await self._execute(search_id, params, record)
        except Exception as exc:  # noqa: BLE001 - recorded and surfaced to the client
            logger.exception("Search %s failed", search_id)
            record.status = "failed"
            # The technical text stays here and in the log; only the translated
            # version is published to the browser.
            record.error = operator_detail(exc)
            record.user_error = user_facing_message(exc, params.lang)
            record.completed_at = datetime.now(UTC)
            await self._session.commit()
            await self._publish(search_id, {"type": "failed", "error": record.user_error})
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        payload["duration_ms"] = duration_ms

        record.status = "complete"
        record.duration_ms = duration_ms
        record.result = payload
        record.completed_at = datetime.now(UTC)
        await self._session.commit()

        await self._publish(
            search_id,
            {
                "type": "complete",
                "search_id": search_id,
                "hidden_option_count": payload["hidden_city"]["count"],
                "best_savings": payload["hidden_city"]["best_savings"],
                "duration_ms": duration_ms,
            },
        )
        return payload

    # ------------------------------------------------------------- internals
    async def _execute(
        self, search_id: str, params: SearchRequestIn, record: SearchQuery
    ) -> dict[str, Any]:
        """Analyse the outbound, and for a return trip the inbound as well.

        A return trip is deliberately **two independent one-way searches**, not
        one round-trip fare. Hidden-city ticketing cannot be used on a
        round-trip: missing a leg cancels every leg after it, including the
        flight home. Buying two one-ways is what makes the technique usable at
        all, so the tool prices what the traveller should actually buy.
        """
        warnings: list[str] = []

        outbound = await self._analyse_leg(
            search_id,
            params,
            record,
            origin=params.origin,
            destination=params.destination,
            departure=params.departure_date,
            leg="outbound",
            warnings=warnings,
        )

        inbound: LegResult | None = None
        if params.is_round_trip:
            assert params.return_date is not None
            inbound = await self._analyse_leg(
                search_id,
                params,
                record,
                # The return flies the same city pair backwards.
                origin=params.destination,
                destination=params.origin,
                departure=params.return_date,
                leg="inbound",
                warnings=warnings,
            )

        best = outbound.analysis.best_option
        record.best_hidden_price = best.price if best else None
        record.best_savings = best.savings if best else None

        return self._render(
            search_id=search_id,
            params=params,
            outbound=outbound,
            inbound=inbound,
            warnings=warnings,
        )

    async def _analyse_leg(
        self,
        search_id: str,
        params: SearchRequestIn,
        record: SearchQuery,
        *,
        origin: str,
        destination: str,
        departure: date,
        leg: str,
        warnings: list[str],
    ) -> LegResult:
        """Price one direction end to end: baseline, candidates, fan-out, analysis."""
        # -- 1. baseline A -> B --------------------------------------------
        baseline_request = self._build_request(params, origin, destination, departure)
        baseline_result = await self._fetch_leg(baseline_request, refresh=params.refresh)

        if not baseline_result.ok:
            raise SearchFailed(
                f"Could not price the direct {origin}->{destination} market: "
                f"{baseline_result.error}"
            )
        if not baseline_result.offers:
            raise SearchFailed(
                f"No flights found for {origin}->{destination} on {departure}. "
                "Without a baseline fare there is nothing to compare against."
            )

        baseline_offers = baseline_result.offers
        baseline_price = min(offer.price_total for offer in baseline_offers)
        if leg == "outbound":
            record.baseline_price = baseline_price
        await self._session.flush()
        await self._publish(
            search_id,
            {
                "type": "baseline",
                "leg": leg,
                "price": round(baseline_price, 2),
                "currency": params.currency,
                "offer_count": len(baseline_offers),
                "from_cache": baseline_result.from_cache,
            },
        )

        # -- 2. candidate destinations C ------------------------------------
        candidates = await generate_candidates(
            self._session,
            origin,
            destination,
            limit=params.max_candidates or settings.max_candidate_destinations,
        )
        record.candidates_planned += len(candidates)
        await self._session.flush()
        await self._publish(
            search_id,
            {
                "type": "candidates",
                "leg": leg,
                "count": len(candidates),
                "candidates": [candidate.to_dict(params.lang) for candidate in candidates],
            },
        )

        if not candidates:
            warnings.append(
                translate("warning.no_candidates", params.lang, destination=destination)
            )

        # -- 3. cache sweep, then concurrent fan-out ------------------------
        requests = [
            self._build_request(params, origin, candidate.iata, departure)
            for candidate in candidates
        ]
        cached: dict[str, ProbeResult] = {}
        pending: list[SearchRequest] = []

        for request in requests:
            hit = None if params.refresh else await self._cache.get(request)
            if hit is None:
                pending.append(request)
            else:
                cached[request.destination] = ProbeResult(
                    request=request, offers=hit, from_cache=True
                )
                await self._publish(
                    search_id,
                    {
                        "type": "probe_finished",
                        "leg": leg,
                        **cached[request.destination].to_dict(),
                    },
                )

        engine = BatchEngine(
            self._provider,
            on_progress=lambda event: self._publish(search_id, {**event, "leg": leg}),
        )
        fresh = await engine.probe_many(pending)

        for result in fresh:
            if result.ok:
                await self._cache.put(result.request, result.offers)

        probes = [cached.get(request.destination) for request in requests]
        fresh_by_destination = {result.destination: result for result in fresh}
        probe_results: list[ProbeResult] = [
            probe or fresh_by_destination[request.destination]
            for probe, request in zip(probes, requests, strict=True)
        ]

        record.candidates_probed += sum(1 for result in probe_results if result.ok)
        failed = [result for result in probe_results if not result.ok]
        if failed:
            warnings.append(
                translate(
                    "warning.failed_probes",
                    params.lang,
                    failed=len(failed),
                    total=len(probe_results),
                )
            )
        await self._session.flush()

        # -- 4. Pandas analysis ---------------------------------------------
        extended_offers: list[Offer] = [
            offer for result in probe_results if result.ok for offer in result.offers
        ]
        analysis = analyse(
            target_iata=destination,
            baseline_offers=baseline_offers,
            extended_offers=extended_offers,
            include_nearby_airports=params.include_nearby_airports,
            min_savings_absolute=params.min_savings_absolute,
            min_savings_percent=params.min_savings_percent,
        )

        # -- 5. persistence & learning --------------------------------------
        await self._persist_findings(record, origin, destination, departure, analysis)
        anomalous_destinations = {
            option.ticketed_iata for option in analysis.hidden_options
        }
        best_by_destination: dict[str, float] = {}
        for option in analysis.hidden_options:
            best_by_destination[option.ticketed_iata] = max(
                best_by_destination.get(option.ticketed_iata, 0.0), option.savings
            )
        await record_probe_outcomes(
            self._session,
            destination,
            [
                ProbeOutcome(
                    onward_iata=result.destination,
                    produced_anomaly=result.destination in anomalous_destinations,
                    savings=best_by_destination.get(result.destination),
                    offer_count=len(result.offers),
                )
                for result in probe_results
                if result.ok
            ],
        )

        return LegResult(
            leg=leg,
            origin=origin,
            destination=destination,
            departure_date=departure,
            analysis=analysis,
            candidates=candidates,
            probe_results=probe_results,
        )

    def _build_request(
        self,
        params: SearchRequestIn,
        origin: str,
        destination: str,
        departure: date,
    ) -> SearchRequest:
        # One-way, always. Even for a return trip the two directions are priced
        # as separate one-way tickets -- see _execute.
        return SearchRequest(
            origin=origin,
            destination=destination,
            departure_date=departure,
            adults=params.adults,
            cabin=params.cabin,
            currency=params.currency,
        )

    async def _fetch_leg(self, request: SearchRequest, *, refresh: bool) -> ProbeResult:
        """Single cached-or-live leg fetch (used for the baseline)."""
        if not refresh:
            cached = await self._cache.get(request)
            if cached is not None:
                return ProbeResult(request=request, offers=cached, from_cache=True)

        engine = BatchEngine(self._provider, concurrency=1)
        result = await engine.probe(request)
        if result.ok:
            await self._cache.put(request, result.offers)
        return result

    async def _persist_findings(
        self,
        record: SearchQuery,
        origin: str,
        destination: str,
        departure: date,
        analysis: AnalysisResult,
    ) -> None:
        for option in analysis.hidden_options:
            self._session.add(
                HiddenCityFinding(
                    search_id=record.id,
                    origin=origin,
                    deplane_iata=option.deplane_iata,
                    ticketed_iata=option.ticketed_iata,
                    departure_date=departure,
                    price=option.price,
                    baseline_price=option.baseline_price,
                    savings=option.savings,
                    savings_percent=option.savings_percent,
                    currency=option.currency,
                    carrier=option.carrier,
                    deplane_segment_index=option.deplane_index,
                    segments_before_target=option.segments_before_target,
                    layover_minutes_at_target=option.layover_minutes,
                    confidence=option.risk.confidence,
                    risk_flags=[flag.code for flag in option.risk.flags],
                    itinerary=option.offer.outbound.to_dict(),
                )
            )
        await self._session.flush()

    def _leg_payload(self, leg: LegResult, lang: str, currency: str) -> dict[str, Any]:
        analysis = leg.analysis
        best = analysis.best_option
        return {
            "leg": leg.leg,
            "origin": leg.origin,
            "destination": leg.destination,
            "departure_date": leg.departure_date.isoformat(),
            "origin_airport": _airport_summary(leg.origin),
            "destination_airport": _airport_summary(leg.destination),
            "baseline": {
                "price": None
                if analysis.baseline_price is None
                else round(analysis.baseline_price, 2),
                "currency": currency,
                "offer_count": len(analysis.baseline_offers),
                "offers": [offer.to_dict() for offer in analysis.baseline_offers],
            },
            "hidden_city": {
                "count": len(analysis.hidden_options),
                "best_savings": None if best is None else round(best.savings, 2),
                "best_savings_percent": None
                if best is None
                else round(best.savings_percent, 1),
                "rejected_count": analysis.rejected_count,
                "options": [option.to_dict(lang) for option in analysis.hidden_options],
            },
            "candidates": [candidate.to_dict(lang) for candidate in leg.candidates],
            "probes": [result.to_dict() for result in leg.probe_results],
            "price_matrix": analysis.price_matrix,
            "market_stats": analysis.market_stats,
        }

    def _render(
        self,
        *,
        search_id: str,
        params: SearchRequestIn,
        outbound: LegResult,
        inbound: LegResult | None,
        warnings: list[str],
    ) -> dict[str, Any]:
        outbound_payload = self._leg_payload(outbound, params.lang, params.currency)

        payload: dict[str, Any] = {
            "search_id": search_id,
            "status": "complete",
            "generated_at": datetime.now(UTC).isoformat(),
            "provider": self._provider.name,
            "language": params.lang,
            "direction": "rtl" if is_rtl(params.lang) else "ltr",
            "trip_type": "round_trip" if params.is_round_trip else "one_way",
            "query": {
                **params.model_dump(mode="json"),
                "origin_airport": _airport_summary(params.origin),
                "destination_airport": _airport_summary(params.destination),
            },
            # The outbound leg is also spread across the top level so a
            # one-way response keeps exactly the shape it always had.
            **{
                key: value
                for key, value in outbound_payload.items()
                if key not in {"leg", "origin", "destination", "departure_date",
                               "origin_airport", "destination_airport"}
            },
            "outbound": outbound_payload,
            "inbound": None,
            "totals": None,
            "disclaimer": disclaimer_payload(params.lang),
            "warnings": warnings,
        }

        if inbound is not None:
            inbound_payload = self._leg_payload(inbound, params.lang, params.currency)
            payload["inbound"] = inbound_payload
            payload["totals"] = self._totals(outbound, inbound, params.currency)

        return payload

    @staticmethod
    def _totals(outbound: LegResult, inbound: LegResult, currency: str) -> dict[str, Any]:
        """What the whole trip costs, normally versus with hidden-city fares.

        The two directions are independent tickets, so the totals simply add --
        and a traveller can take the hidden-city option on one leg, the other,
        or both.
        """

        def cheapest(leg: LegResult) -> tuple[float | None, float | None]:
            baseline = leg.analysis.baseline_price
            best = leg.analysis.best_option
            return baseline, (best.price if best else None)

        out_base, out_best = cheapest(outbound)
        in_base, in_best = cheapest(inbound)

        if out_base is None or in_base is None:
            return {"currency": currency, "baseline": None, "best": None, "savings": None}

        baseline_total = out_base + in_base
        best_total = (out_best if out_best is not None else out_base) + (
            in_best if in_best is not None else in_base
        )
        return {
            "currency": currency,
            "baseline": round(baseline_total, 2),
            "best": round(best_total, 2),
            "savings": round(baseline_total - best_total, 2),
            "legs_with_savings": sum(
                1 for value in (out_best, in_best) if value is not None
            ),
        }

    @staticmethod
    async def _publish(search_id: str, event: dict[str, Any]) -> None:
        await event_bus.publish(search_id, event)
