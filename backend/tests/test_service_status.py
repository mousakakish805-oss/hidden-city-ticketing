"""Retiring markets that no longer have service.

The bundled route graph is a ~2014 snapshot, so it proposes airports that have
since closed. Two mechanisms fix that, and both are tested here: a curated list
for the cold start, and learned suppression for everything else.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.hub_graph import (
    DEAD_MARKET_MIN_PROBES,
    ProbeOutcome,
    load_dead_markets,
    rank_candidates,
    record_probe_outcomes,
)
from app.data.service_status import is_suspended, suspended_codes, suspension_for
from app.db.base import SessionLocal, init_models
from app.db.models import RouteCandidate

DEPART = (date.today() + timedelta(days=45)).isoformat()


# ------------------------------------------------------------ curated list


def test_destroyed_airports_are_marked_suspended() -> None:
    """Donetsk airport was destroyed in 2014; the route dump predates that."""
    assert is_suspended("DOK")
    suspension = suspension_for("DOK")
    assert suspension is not None
    assert suspension.since.startswith("2014")


def test_country_wide_closures_expand_to_their_airports() -> None:
    """Ukrainian airspace has been closed to civil aviation since 2022."""
    for code in ("KBP", "ODS", "DNK", "LWO"):
        assert is_suspended(code), f"{code} should be suspended"


def test_airports_inside_closed_airspace_are_suspended() -> None:
    """Southern Russia is closed while the rest of the country still flies,
    so this cannot be expressed as a country-wide rule."""
    for code in ("ROV", "KRR", "AAQ", "EGO"):
        assert is_suspended(code), f"{code} should be suspended"
    # ...and the rest of Russia is unaffected.
    assert not is_suspended("SVO")
    assert not is_suspended("LED")


def test_operating_airports_are_not_suspended() -> None:
    for code in ("IST", "AMM", "SKP", "SOF", "CDG", "DXB", "ATH", "TGD"):
        assert not is_suspended(code)


def test_suspended_airports_are_never_proposed_as_candidates() -> None:
    """This is the visible bug: Donetsk and Odessa showing up as destinations."""
    codes = {candidate.iata for candidate in rank_candidates("AMM", "IST", limit=40)}

    assert not (codes & suspended_codes())
    assert "DOK" not in codes
    assert "ODS" not in codes


def test_suppression_does_not_empty_the_candidate_list() -> None:
    """Removing dead markets must leave real ones, not break the feature."""
    candidates = rank_candidates("AMM", "IST", limit=12)

    assert len(candidates) >= 8
    assert {"SKP", "SOF", "PRN", "TIA"} & {c.iata for c in candidates}


# --------------------------------------------------------- learned suppression


@pytest.fixture
async def session():
    await init_models()
    async with SessionLocal() as session:
        yield session
        await session.rollback()


async def test_repeatedly_empty_markets_are_retired(session) -> None:
    """Whatever the reason a market died, enough empty probes retire it."""
    for _ in range(DEAD_MARKET_MIN_PROBES):
        await record_probe_outcomes(
            session,
            "XXX",
            [ProbeOutcome("YYY", produced_anomaly=False, savings=None, offer_count=0)],
        )

    assert "YYY" in await load_dead_markets(session, "XXX")


async def test_one_empty_probe_is_not_enough_to_retire_a_market(session) -> None:
    """A single empty response can be a sold-out date, not a dead route."""
    await record_probe_outcomes(
        session,
        "XXA",
        [ProbeOutcome("YYA", produced_anomaly=False, savings=None, offer_count=0)],
    )

    assert "YYA" not in await load_dead_markets(session, "XXA")


async def test_markets_that_return_flights_are_never_retired(session) -> None:
    for _ in range(DEAD_MARKET_MIN_PROBES + 2):
        await record_probe_outcomes(
            session,
            "XXB",
            [ProbeOutcome("YYB", produced_anomaly=False, savings=None, offer_count=6)],
        )

    assert "YYB" not in await load_dead_markets(session, "XXB")


async def test_a_market_that_ever_paid_off_is_kept(session) -> None:
    """Proven savings outrank a run of empty responses."""
    await record_probe_outcomes(
        session,
        "XXC",
        [ProbeOutcome("YYC", produced_anomaly=True, savings=40.0, offer_count=3)],
    )
    for _ in range(DEAD_MARKET_MIN_PROBES + 3):
        await record_probe_outcomes(
            session,
            "XXC",
            [ProbeOutcome("YYC", produced_anomaly=False, savings=None, offer_count=0)],
        )

    assert "YYC" not in await load_dead_markets(session, "XXC")


async def test_empty_counter_is_persisted(session) -> None:
    await record_probe_outcomes(
        session,
        "XXD",
        [ProbeOutcome("YYD", produced_anomaly=False, savings=None, offer_count=0)],
    )

    row = (
        await session.execute(
            select(RouteCandidate)
            .where(RouteCandidate.hub_iata == "XXD")
            .where(RouteCandidate.onward_iata == "YYD")
        )
    ).scalar_one()

    assert row.times_empty == 1
    assert row.times_probed == 1
    assert row.empty_rate == 1.0


async def test_dead_markets_are_excluded_from_ranking() -> None:
    with_dead = rank_candidates("AMM", "IST", limit=40)
    codes = [c.iata for c in with_dead]
    victim = codes[0]

    filtered = rank_candidates("AMM", "IST", limit=40, dead_markets={victim})

    assert victim not in {c.iata for c in filtered}


# ------------------------------------------------------------------- API


async def test_searches_no_longer_surface_closed_airports(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json={"origin": "AMM", "destination": "IST", "departure_date": DEPART},
        )
    ).json()

    ticketed = {option["ticketed_iata"] for option in body["hidden_city"]["options"]}
    probed = {probe["destination"] for probe in body["probes"]}

    assert not (ticketed & suspended_codes())
    assert not (probed & suspended_codes())
    assert body["hidden_city"]["count"] > 0
