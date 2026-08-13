"""HTTP-level tests against the real ASGI app."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

DEPART = (date.today() + timedelta(days=45)).isoformat()


def search_body(**overrides) -> dict:
    return {
        "origin": "AMM",
        "destination": "IST",
        "departure_date": DEPART,
        "adults": 1,
        "cabin": "ECONOMY",
        "currency": "USD",
        **overrides,
    }


# ---------------------------------------------------------------------- system


async def test_health_reports_provider_and_database(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "mock"
    assert body["provider_live"] is False
    assert body["database_reachable"] is True


async def test_disclaimer_is_versioned_and_lists_required_rules(client: AsyncClient) -> None:
    response = await client.get("/api/disclaimer")

    assert response.status_code == 200
    body = response.json()
    assert body["version"]
    codes = {rule["code"] for rule in body["rules"]}
    # The two rules the user must never miss.
    assert {"ONE_WAY_ONLY", "CARRY_ON_ONLY"} <= codes
    assert {"ONE_WAY_ONLY", "CARRY_ON_ONLY"} <= set(body["required_codes"])


# -------------------------------------------------------------------- airports


async def test_airport_autocomplete_ranks_exact_code_first(client: AsyncClient) -> None:
    response = await client.get("/api/airports", params={"q": "ist"})

    assert response.status_code == 200
    results = response.json()
    assert results[0]["iata"] == "IST"
    assert results[0]["city"] == "Istanbul"


async def test_airport_autocomplete_matches_city_names(client: AsyncClient) -> None:
    results = (await client.get("/api/airports", params={"q": "amman"})).json()

    assert {item["iata"] for item in results} >= {"AMM"}


async def test_unknown_airport_returns_404(client: AsyncClient) -> None:
    assert (await client.get("/api/airports/ZZZ")).status_code == 404


async def test_candidate_preview_costs_no_api_calls(client: AsyncClient) -> None:
    response = await client.get("/api/airports/IST/candidates", params={"origin": "AMM"})

    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "IST"
    assert body["count"] > 0
    assert all(candidate["detour_ratio"] <= 1.45 for candidate in body["candidates"])


# --------------------------------------------------------------------- search


async def test_synchronous_search_returns_a_complete_result(client: AsyncClient) -> None:
    response = await client.post("/api/search", params={"wait": "true"}, json=search_body())

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "complete"
    assert body["provider"] == "mock"
    assert body["baseline"]["price"] > 0
    assert body["baseline"]["offers"]
    assert body["candidates"]
    assert body["probes"]
    assert "price_matrix" in body
    assert "disclaimer" in body
    assert body["duration_ms"] >= 0


async def test_search_finds_hidden_city_options_for_a_fortress_hub(client: AsyncClient) -> None:
    body = (
        await client.post("/api/search", params={"wait": "true"}, json=search_body())
    ).json()

    hidden = body["hidden_city"]
    assert hidden["count"] > 0, "AMM->IST should expose hidden-city options"

    option = hidden["options"][0]
    assert option["deplane_iata"] == "IST"
    assert option["ticketed_iata"] != "IST"
    assert option["price"] < body["baseline"]["price"]
    assert option["savings"] > 0
    assert 0 <= option["risk"]["confidence"] <= 100
    assert option["risk"]["flags"]


async def test_every_option_carries_the_mandatory_baggage_and_one_way_warnings(
    client: AsyncClient,
) -> None:
    body = (
        await client.post("/api/search", params={"wait": "true"}, json=search_body())
    ).json()

    for option in body["hidden_city"]["options"]:
        codes = {flag["code"] for flag in option["risk"]["flags"]}
        assert "CARRY_ON_ONLY" in codes
        assert "ONE_WAY_ONLY" in codes


async def test_the_ticketed_itinerary_actually_stops_at_the_target(
    client: AsyncClient,
) -> None:
    """The core invariant: B must be an intermediate stop, never the last one."""
    body = (
        await client.post("/api/search", params={"wait": "true"}, json=search_body())
    ).json()

    for option in body["hidden_city"]["options"]:
        path = option["offer"]["itineraries"][0]["path"]
        assert option["deplane_iata"] in path[1:-1]
        assert path[-1] == option["ticketed_iata"]
        assert path[0] == "AMM"


async def test_asynchronous_search_completes_and_is_retrievable(client: AsyncClient) -> None:
    created = await client.post("/api/search", json=search_body(destination="IST", refresh=True))

    assert created.status_code == 202
    handle = created.json()
    search_id = handle["search_id"]
    assert handle["stream_url"].endswith(f"/search/{search_id}/events")

    for _ in range(100):
        result = (await client.get(f"/api/search/{search_id}")).json()
        if result.get("status") == "complete":
            break
        await asyncio.sleep(0.05)
    else:  # pragma: no cover - only on a hung run
        pytest.fail("background search did not complete in time")

    assert result["hidden_city"]["count"] >= 0
    assert result["search_id"] == search_id


async def test_matrix_endpoint_mirrors_the_search_result(client: AsyncClient) -> None:
    body = (
        await client.post("/api/search", params={"wait": "true"}, json=search_body())
    ).json()

    matrix = (await client.get(f"/api/search/{body['search_id']}/matrix")).json()

    assert matrix["price_matrix"] == body["price_matrix"]
    assert matrix["market_stats"] == body["market_stats"]


async def test_unknown_search_id_returns_404(client: AsyncClient) -> None:
    assert (await client.get("/api/search/does-not-exist")).status_code == 404


# ----------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "overrides",
    [
        {"origin": "AMM", "destination": "AMM"},          # identical endpoints
        {"departure_date": "2020-01-01"},                  # in the past
        {"destination": "ZZZ"},                            # not in reference data
        {"origin": "TOOLONG"},                             # malformed code
        {"adults": 0},                                     # below minimum
        {"cabin": "SPACE"},                                # not a cabin
    ],
)
async def test_invalid_searches_are_rejected(client: AsyncClient, overrides: dict) -> None:
    response = await client.post(
        "/api/search", params={"wait": "true"}, json=search_body(**overrides)
    )

    assert response.status_code == 422


async def test_lowercase_codes_are_accepted_and_normalised(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json=search_body(origin="amm", destination="ist"),
        )
    ).json()

    assert body["query"]["origin"] == "AMM"
    assert body["query"]["destination"] == "IST"


# ------------------------------------------------------------- acknowledgement


async def test_acknowledgement_is_recorded(client: AsyncClient) -> None:
    version = (await client.get("/api/disclaimer")).json()["version"]

    response = await client.post(
        "/api/search/none/acknowledge",
        json={"client_token": "test-client-token", "version": version},
    )

    assert response.status_code == 200
    assert response.json()["acknowledged"] is True


async def test_stale_disclaimer_version_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        "/api/search/none/acknowledge",
        json={"client_token": "test-client-token", "version": "1900.1"},
    )

    assert response.status_code == 409
    assert "out of date" in response.json()["detail"]


# ------------------------------------------------------------ trends & caching


async def test_searches_record_price_observations(client: AsyncClient) -> None:
    await client.post("/api/search", params={"wait": "true"}, json=search_body(refresh=True))

    trend = (
        await client.get("/api/trends", params={"origin": "AMM", "destination": "IST"})
    ).json()

    assert trend["points"]
    assert trend["latest"] > 0
    assert trend["lowest"] <= trend["latest"] <= trend["highest"]


async def test_repeated_searches_are_served_from_cache(client: AsyncClient) -> None:
    await client.post("/api/search", params={"wait": "true"}, json=search_body(refresh=True))
    second = (
        await client.post("/api/search", params={"wait": "true"}, json=search_body())
    ).json()

    assert all(probe["from_cache"] for probe in second["probes"])


async def test_refresh_bypasses_the_cache(client: AsyncClient) -> None:
    await client.post("/api/search", params={"wait": "true"}, json=search_body())
    refreshed = (
        await client.post(
            "/api/search", params={"wait": "true"}, json=search_body(refresh=True)
        )
    ).json()

    assert not any(probe["from_cache"] for probe in refreshed["probes"])


async def test_findings_and_learned_routes_are_persisted(client: AsyncClient) -> None:
    await client.post("/api/search", params={"wait": "true"}, json=search_body())

    findings = (await client.get("/api/trends/findings")).json()
    routes = (await client.get("/api/trends/routes", params={"hub": "IST"})).json()
    summary = (await client.get("/api/trends/summary")).json()

    assert findings["count"] > 0
    assert findings["findings"][0]["savings"] > 0
    assert routes["count"] > 0
    assert summary["total_findings"] > 0
