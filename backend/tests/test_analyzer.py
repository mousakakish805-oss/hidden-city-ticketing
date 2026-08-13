"""The anomaly detector, tested against hand-built itineraries.

Every case here encodes a rule the detector must not get wrong -- most
importantly, that arriving at B as the *final* stop is an ordinary trip, not a
hidden city.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core.analyzer import analyse, offers_to_frame, stopovers_to_frame
from app.providers.base import Itinerary, Offer, Segment

DEPART = date(2026, 9, 1)
BASE_TIME = datetime(2026, 9, 1, 8, 0)


def build_offer(
    path: tuple[str, ...],
    price: float,
    *,
    carrier: str = "TK",
    offer_id: str = "1",
    layovers: tuple[int, ...] = (),
    leg_minutes: int = 120,
    seats: int | None = 5,
    round_trip: bool = False,
    aircraft: str = "32N",
) -> Offer:
    """Assemble an offer whose routing is exactly ``path``."""
    segments: list[Segment] = []
    cursor = BASE_TIME
    for index in range(len(path) - 1):
        arrival = cursor + timedelta(minutes=leg_minutes)
        segments.append(
            Segment(
                origin=path[index],
                destination=path[index + 1],
                departure_at=cursor,
                arrival_at=arrival,
                carrier=carrier,
                flight_number=f"{100 + index}",
                duration_minutes=leg_minutes,
                aircraft=aircraft,
            )
        )
        if index < len(path) - 2:
            gap = layovers[index] if index < len(layovers) else 90
            cursor = arrival + timedelta(minutes=gap)

    total = int((segments[-1].arrival_at - segments[0].departure_at).total_seconds() // 60)
    itinerary = Itinerary(segments=tuple(segments), duration_minutes=total)
    itineraries = (itinerary, itinerary) if round_trip else (itinerary,)

    return Offer(
        provider="test",
        offer_id=offer_id,
        search_origin=path[0],
        search_destination=path[-1],
        departure_date=DEPART,
        price_total=price,
        currency="USD",
        itineraries=itineraries,
        validating_carriers=(carrier,),
        bookable_seats=seats,
    )


@pytest.fixture
def baseline() -> list[Offer]:
    """AMM -> IST direct costs 300."""
    return [build_offer(("AMM", "IST"), 300.0, offer_id="base")]


# --------------------------------------------------------------- core detection


def test_detects_a_cheaper_extended_route_through_the_target(baseline: list[Offer]) -> None:
    extended = [build_offer(("AMM", "IST", "SKP"), 200.0, offer_id="hc")]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert result.baseline_price == 300.0
    assert len(result.hidden_options) == 1
    option = result.hidden_options[0]
    assert option.ticketed_iata == "SKP"
    assert option.deplane_iata == "IST"
    assert option.savings == pytest.approx(100.0)
    assert option.savings_percent == pytest.approx(33.33, abs=0.01)
    assert option.deplane_index == 0
    assert option.segments_after_target == 1


def test_ignores_routes_that_only_end_at_the_target(baseline: list[Offer]) -> None:
    """AMM -> CAI -> IST arrives at IST last. That is just a connecting flight."""
    extended = [build_offer(("AMM", "CAI", "IST"), 150.0, offer_id="normal")]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert result.hidden_options == []


def test_ignores_routes_that_never_touch_the_target(baseline: list[Offer]) -> None:
    extended = [build_offer(("AMM", "CAI", "SKP"), 120.0, offer_id="miss")]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert result.hidden_options == []


def test_ignores_extended_routes_that_cost_more(baseline: list[Offer]) -> None:
    extended = [build_offer(("AMM", "IST", "SKP"), 420.0, offer_id="pricier")]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert result.hidden_options == []


def test_finds_the_target_deep_in_a_multi_stop_itinerary(baseline: list[Offer]) -> None:
    """AMM -> CAI -> IST -> SKP: IST is an intermediate stop, so it qualifies."""
    extended = [build_offer(("AMM", "CAI", "IST", "SKP"), 200.0, offer_id="deep")]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert len(result.hidden_options) == 1
    option = result.hidden_options[0]
    assert option.deplane_index == 1
    assert option.segments_before_target == 1
    # A connection before the target is the dominant execution risk.
    assert option.risk.confidence < 80
    assert "REROUTE_RISK" in {flag.code for flag in option.risk.flags}


# ------------------------------------------------------------------ thresholds


def test_savings_below_the_absolute_floor_are_suppressed(baseline: list[Offer]) -> None:
    extended = [build_offer(("AMM", "IST", "SKP"), 295.0, offer_id="tiny")]

    result = analyse(
        target_iata="IST",
        baseline_offers=baseline,
        extended_offers=extended,
        min_savings_absolute=15.0,
        min_savings_percent=0.0,
    )

    assert result.hidden_options == []
    assert result.rejected_count == 1


def test_savings_below_the_percentage_floor_are_suppressed(baseline: list[Offer]) -> None:
    extended = [build_offer(("AMM", "IST", "SKP"), 280.0, offer_id="thin")]

    result = analyse(
        target_iata="IST",
        baseline_offers=baseline,
        extended_offers=extended,
        min_savings_absolute=0.0,
        min_savings_percent=10.0,
    )

    assert result.hidden_options == []


def test_thresholds_can_be_relaxed_per_search(baseline: list[Offer]) -> None:
    extended = [build_offer(("AMM", "IST", "SKP"), 295.0, offer_id="tiny")]

    result = analyse(
        target_iata="IST",
        baseline_offers=baseline,
        extended_offers=extended,
        min_savings_absolute=1.0,
        min_savings_percent=1.0,
    )

    assert len(result.hidden_options) == 1


def test_round_trip_offers_are_rejected(baseline: list[Offer]) -> None:
    """Deplaning early on a round-trip cancels the return, so it must never surface."""
    extended = [build_offer(("AMM", "IST", "SKP"), 180.0, offer_id="rt", round_trip=True)]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert result.hidden_options == []


def test_impossibly_short_ground_time_is_rejected(baseline: list[Offer]) -> None:
    extended = [
        build_offer(("AMM", "IST", "SKP"), 180.0, offer_id="rush", layovers=(5,))
    ]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert result.hidden_options == []


# ------------------------------------------------------------ nearby airports


def test_nearby_metro_airport_is_excluded_by_default(baseline: list[Offer]) -> None:
    """SAW is 50 km from IST; only count it when the user opts in."""
    extended = [build_offer(("AMM", "SAW", "SKP"), 180.0, offer_id="saw")]

    strict = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)
    assert strict.hidden_options == []

    relaxed = analyse(
        target_iata="IST",
        baseline_offers=baseline,
        extended_offers=extended,
        include_nearby_airports=True,
    )
    assert len(relaxed.hidden_options) == 1
    assert relaxed.hidden_options[0].is_nearby_airport is True


# ------------------------------------------------------------- ranking / shape


def test_results_are_deduplicated_per_route_and_carrier(baseline: list[Offer]) -> None:
    extended = [
        build_offer(("AMM", "IST", "SKP"), 200.0, offer_id="a"),
        build_offer(("AMM", "IST", "SKP"), 210.0, offer_id="b"),
        build_offer(("AMM", "IST", "SKP"), 190.0, offer_id="c"),
    ]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert len(result.hidden_options) == 1
    assert result.hidden_options[0].price == 190.0


def test_ranking_prefers_a_safer_option_over_a_marginally_cheaper_one(
    baseline: list[Offer],
) -> None:
    """A slightly cheaper fare is not worth a routing that may skip the target."""
    extended = [
        build_offer(("AMM", "IST", "SKP"), 205.0, offer_id="safe", carrier="TK"),
        build_offer(("AMM", "CAI", "IST", "SOF"), 200.0, offer_id="risky", carrier="MS"),
    ]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    assert [option.ticketed_iata for option in result.hidden_options] == ["SKP", "SOF"]


def test_baseline_uses_the_cheapest_direct_fare() -> None:
    baseline = [
        build_offer(("AMM", "IST"), 300.0, offer_id="b1"),
        build_offer(("AMM", "CAI", "IST"), 240.0, offer_id="b2", carrier="MS"),
    ]
    extended = [build_offer(("AMM", "IST", "SKP"), 250.0, offer_id="hc")]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    # 250 beats the 300 nonstop but loses to the 240 one-stop, so it is no saving.
    assert result.baseline_price == 240.0
    assert result.hidden_options == []


def test_empty_inputs_produce_an_empty_but_valid_result() -> None:
    result = analyse(target_iata="IST", baseline_offers=[], extended_offers=[])

    assert result.baseline_price is None
    assert result.hidden_options == []
    assert result.price_matrix["rows"] == []
    assert result.market_stats == []


# ---------------------------------------------------------------- frames / matrix


def test_stopover_frame_excludes_the_final_arrival() -> None:
    offers = [build_offer(("AMM", "CAI", "IST", "SKP"), 200.0)]

    frame = stopovers_to_frame(offers)

    assert list(frame["deplane_iata"]) == ["CAI", "IST"]
    assert list(frame["deplane_index"]) == [0, 1]


def test_offer_frame_records_the_full_routing() -> None:
    frame = offers_to_frame([build_offer(("AMM", "IST", "SKP"), 200.0)])

    assert frame.loc[0, "path"] == "AMM-IST-SKP"
    assert frame.loc[0, "stops"] == 1
    assert frame.loc[0, "n_segments"] == 2


def test_price_matrix_marks_the_target_row(baseline: list[Offer]) -> None:
    extended = [
        build_offer(("AMM", "IST", "SKP"), 200.0, carrier="TK"),
        build_offer(("AMM", "IST", "SOF"), 220.0, carrier="MS", offer_id="2"),
    ]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)
    matrix = result.price_matrix

    assert set(matrix["destinations"]) == {"IST", "SKP", "SOF"}
    assert sorted(matrix["carriers"]) == ["MS", "TK"]
    target_row = next(row for row in matrix["rows"] if row["is_target"])
    assert target_row["iata"] == "IST"
    assert target_row["cheapest"] == 300.0
    # Cheapest destination first, so the target must not lead.
    assert matrix["rows"][0]["iata"] != "IST"


def test_market_stats_summarise_every_probed_destination(baseline: list[Offer]) -> None:
    extended = [
        build_offer(("AMM", "IST", "SKP"), 200.0, offer_id="1"),
        build_offer(("AMM", "IST", "SKP"), 260.0, offer_id="2", carrier="MS"),
    ]

    result = analyse(target_iata="IST", baseline_offers=baseline, extended_offers=extended)

    skp = next(stat for stat in result.market_stats if stat["iata"] == "SKP")
    assert skp["offer_count"] == 2
    assert skp["min_price"] == 200.0
    assert skp["median_price"] == 230.0
    assert skp["carriers"] == 2
