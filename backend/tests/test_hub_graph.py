"""Candidate generation: which onward cities C are worth an API call."""

from __future__ import annotations

from app.core.hub_graph import rank_candidates
from app.data.airports import get_airport


def codes(candidates) -> list[str]:
    return [candidate.iata for candidate in candidates]


def test_generates_onward_markets_beyond_a_hub() -> None:
    candidates = rank_candidates("AMM", "IST", limit=12)

    assert candidates
    # Balkan cities behind the Istanbul hub are the classic opportunity.
    assert {"SKP", "SOF", "PRN", "TIA"} & set(codes(candidates))


def test_ranking_rejects_markets_that_are_further_without_being_cheaper() -> None:
    """A big airport well beyond the hub costs more to reach, so it must not win.

    Hannover is larger than Skopje and sits behind Istanbul, but it is roughly
    twice as far from Amman -- the extra distance swamps its lower demand.
    """
    codes_by_rank = codes(rank_candidates("AMM", "IST", limit=12))

    assert "SKP" in codes_by_rank
    assert "HAJ" not in codes_by_rank


def test_thin_markets_without_real_service_are_not_probed() -> None:
    """Every API call costs money; airstrips cannot produce a through-fare."""
    from app.data.airports import get_airport

    for candidate in rank_candidates("AMM", "IST", limit=40):
        airport = get_airport(candidate.iata)
        assert airport is not None
        assert airport.destination_count >= 6


def test_never_proposes_the_origin_or_the_target() -> None:
    candidates = rank_candidates("AMM", "IST", limit=40)

    assert "AMM" not in codes(candidates)
    assert "IST" not in codes(candidates)


def test_excludes_other_airports_in_the_targets_metro_area() -> None:
    """Ticketing to SAW to reach IST is not a hidden city -- it is a different airport."""
    candidates = rank_candidates("AMM", "IST", limit=40)

    assert "SAW" not in codes(candidates)


def test_excludes_airports_in_the_origins_metro_area() -> None:
    candidates = rank_candidates("LHR", "FRA", limit=40)

    assert not {"LGW", "STN"} & set(codes(candidates))


def test_every_candidate_lies_beyond_the_target() -> None:
    origin, target = get_airport("AMM"), get_airport("IST")
    assert origin and target

    from app.core.geo import haversine_km

    origin_target_km = haversine_km(origin.lat, origin.lon, target.lat, target.lon)
    for candidate in rank_candidates("AMM", "IST", limit=40):
        assert candidate.total_km > origin_target_km


def test_every_candidate_keeps_the_target_roughly_en_route() -> None:
    from app.config import settings

    for candidate in rank_candidates("AMM", "IST", limit=40):
        assert candidate.detour_ratio <= settings.max_detour_ratio


def test_backtracking_destinations_are_not_proposed() -> None:
    """Flying AMM -> IST -> DXB doubles back, so DXB must never be a candidate."""
    assert "DXB" not in codes(rank_candidates("AMM", "IST", limit=40))


def test_geometry_covers_targets_with_no_route_data() -> None:
    """Airports missing from the route snapshot must still produce candidates."""
    from app.data.airports import all_airports
    from app.data.routes import onward_markets

    # Pick a real airport that has no outbound routes recorded.
    unserved = next(
        airport
        for airport in all_airports()
        if not onward_markets(airport.iata) and airport.country == "Germany"
    )
    candidates = rank_candidates("AMM", unserved.iata, limit=10)

    assert all(candidate.source == "geometric" for candidate in candidates)


def test_route_graph_candidates_are_preferred_over_geometric_ones() -> None:
    candidates = rank_candidates("AMM", "IST", limit=15)
    sources = [candidate.source for candidate in candidates]

    assert "route" in sources
    # Ranking is score-ordered, and route-graph candidates carry a source bonus.
    assert sources.index("route") == 0


def test_learned_edges_outrank_their_geometric_twins() -> None:
    plain = rank_candidates("AMM", "IST", limit=40)
    boosted = rank_candidates("AMM", "IST", limit=40, learned={"KIV": 2.0})

    plain_rank = codes(plain).index("KIV")
    boosted_rank = codes(boosted).index("KIV")
    assert boosted_rank < plain_rank
    assert next(c for c in boosted if c.iata == "KIV").source == "learned"


def test_limit_is_respected() -> None:
    assert len(rank_candidates("AMM", "IST", limit=3)) == 3


def test_unknown_airports_yield_no_candidates() -> None:
    assert rank_candidates("AMM", "ZZZ", limit=5) == []
    assert rank_candidates("ZZZ", "IST", limit=5) == []


def test_candidates_are_ordered_by_score() -> None:
    scores = [candidate.score for candidate in rank_candidates("AMM", "IST", limit=12)]
    assert scores == sorted(scores, reverse=True)
