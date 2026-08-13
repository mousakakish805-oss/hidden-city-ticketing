"""Price-anomaly analysis over normalised offers, using Pandas.

The pipeline is deliberately tabular rather than a nest of Python loops:

    offers  ->  offer frame  ->  stopover frame  ->  joined against baseline
            ->  vectorised savings  ->  dedupe  ->  ranked options

Working in a DataFrame keeps the comparison itself a couple of vectorised
expressions, and gives the comparative price matrix and the per-market
statistics almost for free via ``groupby`` / ``pivot_table``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.config import settings
from app.core.scoring import RiskAssessment, assess
from app.data.airlines import airline_booking_url, airline_name
from app.data.airports import get_airport, sibling_airports
from app.i18n import DEFAULT_LANGUAGE, translate
from app.providers.base import Offer, format_minutes

OFFER_COLUMNS = [
    "offer_key", "provider", "offer_id", "search_origin", "search_destination",
    "price", "currency", "carrier", "n_segments", "stops", "duration_min",
    "depart_at", "arrive_at", "path", "bookable_seats", "is_one_way", "offer",
]

STOP_COLUMNS = [
    "offer_key", "deplane_iata", "deplane_index", "layover_min",
    "usable_duration_min", "usable_arrival",
]


# --------------------------------------------------------------------- frames


def offers_to_frame(offers: Iterable[Offer]) -> pd.DataFrame:
    """One row per offer, with the source object retained for rendering."""
    records: list[dict[str, Any]] = []
    for index, offer in enumerate(offers):
        itinerary = offer.outbound
        records.append(
            {
                "offer_key": f"{offer.search_destination}:{offer.offer_id}:{index}",
                "provider": offer.provider,
                "offer_id": offer.offer_id,
                "search_origin": offer.search_origin,
                "search_destination": offer.search_destination,
                "price": float(offer.price_total),
                "currency": offer.currency,
                "carrier": offer.primary_carrier,
                "n_segments": len(itinerary.segments),
                "stops": itinerary.stop_count,
                "duration_min": int(itinerary.duration_minutes),
                "depart_at": itinerary.segments[0].departure_at,
                "arrive_at": itinerary.segments[-1].arrival_at,
                "path": "-".join(itinerary.path),
                "bookable_seats": offer.bookable_seats,
                "is_one_way": offer.is_one_way,
                "offer": offer,
            }
        )

    if not records:
        return pd.DataFrame(columns=OFFER_COLUMNS)
    return pd.DataFrame.from_records(records)


def stopovers_to_frame(offers: Iterable[Offer]) -> pd.DataFrame:
    """One row per *intermediate* arrival across all offers.

    The final segment is excluded on purpose: arriving at the ticketed
    destination is not a hidden city, it is just the trip.
    """
    records: list[dict[str, Any]] = []
    for index, offer in enumerate(offers):
        itinerary = offer.outbound
        segments = itinerary.segments
        offer_key = f"{offer.search_destination}:{offer.offer_id}:{index}"
        for position, segment in enumerate(segments[:-1]):
            records.append(
                {
                    "offer_key": offer_key,
                    "deplane_iata": segment.destination,
                    "deplane_index": position,
                    "layover_min": itinerary.layover_minutes_after(position),
                    "usable_duration_min": int(
                        (segment.arrival_at - segments[0].departure_at).total_seconds() // 60
                    ),
                    "usable_arrival": segment.arrival_at,
                }
            )

    if not records:
        return pd.DataFrame(columns=STOP_COLUMNS)
    return pd.DataFrame.from_records(records)


# ---------------------------------------------------------------- result types


@dataclass(slots=True)
class HiddenCityOption:
    """A validated A->C-via-B itinerary that undercuts the direct A->B fare."""

    offer: Offer
    ticketed_iata: str
    ticketed_city: str
    deplane_iata: str
    deplane_city: str
    price: float
    baseline_price: float
    savings: float
    savings_percent: float
    currency: str
    carrier: str
    deplane_index: int
    segments_before_target: int
    segments_after_target: int
    layover_minutes: int | None
    usable_duration_minutes: int
    usable_arrival: str
    is_nearby_airport: bool
    risk: RiskAssessment

    def booking(self, lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
        """Where and how to buy this fare.

        We link to the airline's own site rather than a deep link into its
        booking flow, and spell out the search to run -- ticketed destination,
        one way, connecting at the city you actually want. Nothing here books
        anything; this app only reports prices.
        """
        url = airline_booking_url(self.carrier)
        return {
            "carrier": self.carrier,
            "carrier_name": airline_name(self.carrier),
            "url": url,
            "instructions": translate(
                "booking.instructions",
                lang,
                origin=self.offer.search_origin,
                ticketed_iata=self.ticketed_iata,
                deplane_iata=self.deplane_iata,
                date=self.offer.departure_date.isoformat(),
            ),
            "note": (
                None
                if url
                else translate(
                    "booking.no_site", lang, carrier_name=airline_name(self.carrier)
                )
            ),
        }

    def to_dict(self, lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
        return {
            "ticketed_iata": self.ticketed_iata,
            "ticketed_city": self.ticketed_city,
            "deplane_iata": self.deplane_iata,
            "deplane_city": self.deplane_city,
            "price": round(self.price, 2),
            "baseline_price": round(self.baseline_price, 2),
            "savings": round(self.savings, 2),
            "savings_percent": round(self.savings_percent, 1),
            "currency": self.currency,
            "carrier": self.carrier,
            "deplane_index": self.deplane_index,
            "segments_before_target": self.segments_before_target,
            "segments_after_target": self.segments_after_target,
            "layover_minutes": self.layover_minutes,
            "usable_duration_minutes": self.usable_duration_minutes,
            "usable_duration_label": format_minutes(self.usable_duration_minutes),
            "usable_arrival": self.usable_arrival,
            "is_nearby_airport": self.is_nearby_airport,
            "risk": self.risk.to_dict(lang),
            "booking": self.booking(lang),
            "offer": self.offer.to_dict(),
        }


@dataclass(slots=True)
class AnalysisResult:
    baseline_offers: list[Offer]
    baseline_price: float | None
    hidden_options: list[HiddenCityOption]
    price_matrix: dict[str, Any]
    market_stats: list[dict[str, Any]]
    rejected_count: int

    @property
    def best_option(self) -> HiddenCityOption | None:
        return self.hidden_options[0] if self.hidden_options else None


# ------------------------------------------------------------------- analysis


def accepted_target_codes(target_iata: str, *, include_nearby: bool) -> set[str]:
    """Which arrival airports count as "reaching B"."""
    codes = {target_iata.upper()}
    if include_nearby:
        codes.update(sibling_airports(target_iata))
    return codes


def analyse(
    *,
    target_iata: str,
    baseline_offers: Sequence[Offer],
    extended_offers: Sequence[Offer],
    include_nearby_airports: bool = False,
    min_savings_absolute: float | None = None,
    min_savings_percent: float | None = None,
) -> AnalysisResult:
    """Compare extended A->C itineraries against the direct A->B baseline."""
    min_abs = (
        settings.min_savings_absolute if min_savings_absolute is None else min_savings_absolute
    )
    min_pct = (
        settings.min_savings_percent if min_savings_percent is None else min_savings_percent
    )

    baseline_frame = offers_to_frame(baseline_offers)
    baseline_price = float(baseline_frame["price"].min()) if not baseline_frame.empty else None

    extended_frame = offers_to_frame(extended_offers)
    stop_frame = stopovers_to_frame(extended_offers)

    price_matrix = build_price_matrix(baseline_frame, extended_frame, target_iata)
    market_stats = build_market_stats(baseline_frame, extended_frame, target_iata)

    if baseline_price is None or extended_frame.empty or stop_frame.empty:
        return AnalysisResult(
            baseline_offers=list(baseline_offers),
            baseline_price=baseline_price,
            hidden_options=[],
            price_matrix=price_matrix,
            market_stats=market_stats,
            rejected_count=0,
        )

    targets = accepted_target_codes(target_iata, include_nearby=include_nearby_airports)

    # --- the comparison itself, as a join plus two vectorised expressions ---
    candidates = stop_frame[stop_frame["deplane_iata"].isin(targets)].merge(
        extended_frame, on="offer_key", how="inner", validate="many_to_one"
    )
    total_candidates = len(candidates)
    if candidates.empty:
        return AnalysisResult(
            baseline_offers=list(baseline_offers),
            baseline_price=baseline_price,
            hidden_options=[],
            price_matrix=price_matrix,
            market_stats=market_stats,
            rejected_count=0,
        )

    candidates["baseline_price"] = baseline_price
    candidates["savings"] = baseline_price - candidates["price"]
    candidates["savings_percent"] = candidates["savings"] / baseline_price * 100.0

    qualifies = (
        (candidates["savings"] >= min_abs)
        & (candidates["savings_percent"] >= min_pct)
        & (candidates["is_one_way"])
        & (candidates["usable_duration_min"] <= settings.max_usable_duration_minutes)
        # A stop too brief to deplane is not a usable opportunity.
        & (
            candidates["layover_min"].isna()
            | (candidates["layover_min"] >= settings.min_layover_minutes_at_target)
        )
    )
    winners = candidates[qualifies].copy()
    rejected_count = total_candidates - len(winners)

    if winners.empty:
        return AnalysisResult(
            baseline_offers=list(baseline_offers),
            baseline_price=baseline_price,
            hidden_options=[],
            price_matrix=price_matrix,
            market_stats=market_stats,
            rejected_count=rejected_count,
        )

    # Keep only the cheapest itinerary per (ticketed destination, deplane point,
    # carrier) so the UI shows distinct opportunities, not fare-bucket noise.
    winners = (
        winners.sort_values(["price", "deplane_index", "usable_duration_min"])
        .groupby(["search_destination", "deplane_iata", "carrier"], as_index=False, sort=False)
        .head(1)
        .sort_values(["savings", "deplane_index"], ascending=[False, True])
        .reset_index(drop=True)
    )

    target_airport = get_airport(target_iata)
    options: list[HiddenCityOption] = []
    for row in winners.itertuples(index=False):
        ticketed = get_airport(row.search_destination)
        deplane = get_airport(row.deplane_iata)
        ticketed_city = ticketed.city if ticketed else row.search_destination
        deplane_city = deplane.city if deplane else row.deplane_iata
        layover = None if pd.isna(row.layover_min) else int(row.layover_min)

        risk = assess(
            deplane_index=int(row.deplane_index),
            total_segments=int(row.n_segments),
            layover_minutes=layover,
            savings_percent=float(row.savings_percent),
            bookable_seats=(
                None if pd.isna(row.bookable_seats) else int(row.bookable_seats)
            ),
            is_one_way=bool(row.is_one_way),
            deplane_city=deplane_city,
            ticketed_city=ticketed_city,
        )

        options.append(
            HiddenCityOption(
                offer=row.offer,
                ticketed_iata=row.search_destination,
                ticketed_city=ticketed_city,
                deplane_iata=row.deplane_iata,
                deplane_city=deplane_city,
                price=float(row.price),
                baseline_price=baseline_price,
                savings=float(row.savings),
                savings_percent=float(row.savings_percent),
                currency=row.currency,
                carrier=row.carrier,
                deplane_index=int(row.deplane_index),
                segments_before_target=int(row.deplane_index),
                segments_after_target=int(row.n_segments) - int(row.deplane_index) - 1,
                layover_minutes=layover,
                usable_duration_minutes=int(row.usable_duration_min),
                usable_arrival=row.usable_arrival.isoformat(),
                is_nearby_airport=(
                    target_airport is not None and row.deplane_iata != target_airport.iata
                ),
                risk=risk,
            )
        )

    # Final ordering blends money saved with how safely it can be executed: a
    # marginally cheaper option that is likely to reroute around B is worse.
    options.sort(key=lambda option: (-(option.savings * (0.5 + option.risk.confidence / 200)),))

    return AnalysisResult(
        baseline_offers=list(baseline_offers),
        baseline_price=baseline_price,
        hidden_options=options,
        price_matrix=price_matrix,
        market_stats=market_stats,
        rejected_count=rejected_count,
    )


# ------------------------------------------------------------ presentation ---


def build_price_matrix(
    baseline_frame: pd.DataFrame,
    extended_frame: pd.DataFrame,
    target_iata: str,
) -> dict[str, Any]:
    """Ticketed destination x operating carrier -> cheapest fare seen."""
    frames = [frame for frame in (baseline_frame, extended_frame) if not frame.empty]
    if not frames:
        return {"destinations": [], "carriers": [], "rows": [], "currency": None}

    combined = pd.concat(frames, ignore_index=True)
    pivot = combined.pivot_table(
        index="search_destination", columns="carrier", values="price", aggfunc="min"
    )
    # Cheapest destination first; the target's own row anchors the comparison.
    pivot = pivot.reindex(pivot.min(axis=1).sort_values().index)

    carriers = [str(carrier) for carrier in pivot.columns]
    rows: list[dict[str, Any]] = []
    for destination, series in pivot.iterrows():
        airport = get_airport(str(destination))
        rows.append(
            {
                "iata": str(destination),
                "city": airport.city if airport else str(destination),
                "is_target": str(destination) == target_iata.upper(),
                "cheapest": round(float(series.min()), 2),
                "prices": [
                    None if pd.isna(value) else round(float(value), 2) for value in series
                ],
            }
        )

    return {
        "destinations": [row["iata"] for row in rows],
        "carriers": carriers,
        "rows": rows,
        "currency": str(combined["currency"].iloc[0]),
    }


def build_market_stats(
    baseline_frame: pd.DataFrame,
    extended_frame: pd.DataFrame,
    target_iata: str,
) -> list[dict[str, Any]]:
    """Per-destination price distribution across everything we fetched."""
    frames = [frame for frame in (baseline_frame, extended_frame) if not frame.empty]
    if not frames:
        return []

    combined = pd.concat(frames, ignore_index=True)
    grouped = (
        combined.groupby("search_destination")
        .agg(
            offer_count=("price", "size"),
            min_price=("price", "min"),
            median_price=("price", "median"),
            max_price=("price", "max"),
            carriers=("carrier", "nunique"),
            min_stops=("stops", "min"),
        )
        .sort_values("min_price")
        .reset_index()
    )

    stats: list[dict[str, Any]] = []
    for row in grouped.itertuples(index=False):
        airport = get_airport(row.search_destination)
        stats.append(
            {
                "iata": row.search_destination,
                "city": airport.city if airport else row.search_destination,
                "country": airport.country if airport else None,
                "is_target": row.search_destination == target_iata.upper(),
                "offer_count": int(row.offer_count),
                "min_price": round(float(row.min_price), 2),
                "median_price": round(float(row.median_price), 2),
                "max_price": round(float(row.max_price), 2),
                "carriers": int(row.carriers),
                "min_stops": int(row.min_stops),
            }
        )
    return stats
