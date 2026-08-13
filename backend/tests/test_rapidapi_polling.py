"""Retrying the incomplete search on the Skyscanner-derived listing.

The first ``searchFlights`` call *starts* a search server-side and returns a
fragment. A real AMM->IST probe came back with one 19-hour routing via Dubai
and ``direct.isPresent = false``, for a pair two airlines fly nonstop daily.
The identical request moments later returned nine itineraries including the
direct flights.

That is not a missing-options problem, it is a *correctness* problem: a
truncated response corrupts the baseline fare, and every saving this app
reports is measured against that baseline.

The listing has no polling endpoint (``searchIncomplete`` returns 404), so the
retry is a re-issue of ``searchFlights`` with identical parameters. And
completion is judged by *result count*, not by ``context.status`` -- that flag
was observed stuck on ``"incomplete"`` across three retries that all returned
the same 8 itineraries.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from app.providers.base import SearchRequest
from app.providers.rapidapi import RapidApiProvider
from tests.test_rapidapi import CONNECTING_ITINERARY, airport_response, segment

DEPART = date.today() + timedelta(days=45)
REQUEST = SearchRequest(origin="AMM", destination="SKP", departure_date=DEPART)

# What the first call actually returns: one poor routing, no direct flight.
FRAGMENT_ITINERARY = {
    "id": "itin-fragment",
    "price": {"raw": 656.47},
    "isSelfTransfer": False,
    "legs": [
        {
            "id": "leg-fragment",
            "durationInMinutes": 1130,
            "stopCount": 1,
            "carriers": {"marketing": [{"name": "flydubai", "alternateId": "FZ"}]},
            "segments": [
                segment("AMM", "DXB", "2026-09-01T22:35:00", "2026-09-02T02:40:00", 245, "692"),
                segment("DXB", "SKP", "2026-09-02T09:00:00", "2026-09-02T13:25:00", 385, "1729"),
            ],
        }
    ],
}


def build(handler, tmp_path) -> RapidApiProvider:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://sky-scrapper.p.rapidapi.com"
    )
    return RapidApiProvider(
        "key", "sky-scrapper.p.rapidapi.com", client=client, place_cache_path=tmp_path / "p.json"
    )


def staged_handler(stages: list[dict], calls: list[str] | None = None):
    """Serve `stages` in order across the initial search and each poll."""
    state = {"index": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if calls is not None:
            calls.append(path)
        if "searchAirport" in path:
            return httpx.Response(200, json=airport_response(request.url.params["query"]))
        stage = stages[min(state["index"], len(stages) - 1)]
        state["index"] += 1
        return httpx.Response(200, json=stage)

    return handler


def stage(itineraries: list[dict], status: str, session: str | None = "sess-1") -> dict:
    context: dict = {"status": status}
    if session:
        context["sessionId"] = session
    return {"status": True, "data": {"context": context, "itineraries": itineraries}}


async def test_incomplete_first_response_is_retried(tmp_path) -> None:
    calls: list[str] = []
    handler = staged_handler(
        [
            stage([FRAGMENT_ITINERARY], "incomplete"),
            stage([FRAGMENT_ITINERARY, CONNECTING_ITINERARY], "complete"),
        ],
        calls,
    )
    provider = build(handler, tmp_path)

    offers = await provider.search(REQUEST)

    assert calls.count("/api/v1/flights/searchFlights") == 2
    # The complete set, not the fragment.
    assert len(offers) == 2
    await provider.aclose()


async def test_retrying_stops_when_results_stop_growing(tmp_path, monkeypatch) -> None:
    """The status flag stays "incomplete" forever on this listing, so a stable
    result count is the only usable signal that the search has settled."""
    from app.config import settings

    monkeypatch.setattr(settings, "rapidapi_max_polls", 4)
    calls: list[str] = []
    handler = staged_handler(
        [
            stage([], "incomplete"),
            stage([FRAGMENT_ITINERARY, CONNECTING_ITINERARY], "incomplete"),
            stage([FRAGMENT_ITINERARY, CONNECTING_ITINERARY], "incomplete"),
            stage([FRAGMENT_ITINERARY, CONNECTING_ITINERARY], "incomplete"),
        ],
        calls,
    )
    provider = build(handler, tmp_path)

    offers = await provider.search(REQUEST)

    searches = [c for c in calls if c.endswith("searchFlights")]
    # Initial + one growing retry + one that showed no growth, then stop --
    # not the full budget of 4.
    assert len(searches) == 3
    assert len(offers) == 2
    await provider.aclose()


async def test_retrying_is_capped_when_results_never_arrive(tmp_path, monkeypatch) -> None:
    """An empty search must not spend quota without limit."""
    from app.config import settings

    monkeypatch.setattr(settings, "rapidapi_max_polls", 3)
    calls: list[str] = []
    handler = staged_handler([stage([], "incomplete")], calls)
    provider = build(handler, tmp_path)

    await provider.search(REQUEST)

    searches = [c for c in calls if c.endswith("searchFlights")]
    assert len(searches) == settings.rapidapi_max_polls + 1
    await provider.aclose()


async def test_one_retry_is_the_default_budget(tmp_path) -> None:
    """Evidence-based: an observed search reached its full result set on the
    first retry, and two more added nothing."""
    from app.config import settings

    assert settings.rapidapi_max_polls == 1

    calls: list[str] = []
    handler = staged_handler(
        [stage([], "incomplete"), stage([CONNECTING_ITINERARY], "incomplete")], calls
    )
    provider = build(handler, tmp_path)

    offers = await provider.search(REQUEST)

    assert len([c for c in calls if c.endswith("searchFlights")]) == 2
    assert len(offers) == 1
    await provider.aclose()


async def test_empty_retry_does_not_discard_what_we_already_have(tmp_path, monkeypatch) -> None:
    """A retry that returns less must not leave the search worse off."""
    from app.config import settings

    monkeypatch.setattr(settings, "rapidapi_max_polls", 2)
    handler = staged_handler(
        [stage([FRAGMENT_ITINERARY], "incomplete"), stage([], "incomplete")]
    )
    provider = build(handler, tmp_path)

    offers = await provider.search(REQUEST)

    assert len(offers) == 1
    await provider.aclose()


async def test_failed_retry_falls_back_to_the_fragment(tmp_path) -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "searchAirport" in request.url.path:
            return httpx.Response(200, json=airport_response(request.url.params["query"]))
        state["calls"] += 1
        if state["calls"] > 1:
            return httpx.Response(400, json={"message": "search expired"})
        return httpx.Response(200, json=stage([FRAGMENT_ITINERARY], "incomplete"))

    provider = build(handler, tmp_path)

    offers = await provider.search(REQUEST)

    # Degraded, but still an answer rather than an exception.
    assert len(offers) == 1
    await provider.aclose()
