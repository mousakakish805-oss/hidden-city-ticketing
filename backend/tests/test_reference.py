"""Global reference data: airports, airlines, countries and the route graph."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.data.airlines import airline_name, all_airlines, get_airline
from app.data.airports import all_airports, get_airport, search_airports
from app.data.countries import all_countries, get_country
from app.data.routes import connects_via, has_route, one_stop_hubs, onward_markets

# ------------------------------------------------------------------- coverage


def test_dataset_covers_the_world_not_a_curated_shortlist() -> None:
    airports = all_airports()
    countries = {airport.country for airport in airports}

    assert len(airports) > 5000
    assert len(countries) > 200
    assert len(all_airlines()) > 1000
    assert len(all_countries()) > 200


def test_every_continent_is_represented() -> None:
    regions = {airport.region for airport in all_airports()}

    assert {"Europe", "Asia", "Africa", "Americas", "Oceania"} <= regions


@pytest.mark.parametrize(
    ("iata", "city", "country"),
    [
        ("AMM", "Amman", "Jordan"),
        ("IST", "Istanbul", "Turkey"),
        ("GRU", "Sao Paulo", "Brazil"),
        ("NBO", "Nairobi", "Kenya"),
        ("AKL", "Auckland", "New Zealand"),
        ("KTM", "Kathmandu", "Nepal"),
        ("ULN", "Ulan Bator", "Mongolia"),
    ],
)
def test_airports_across_every_region_resolve(iata: str, city: str, country: str) -> None:
    airport = get_airport(iata)

    assert airport is not None
    assert airport.city == city
    assert airport.country == country


# ------------------------------------------------------------------- ranking


def test_search_prefers_the_busiest_airport_for_an_ambiguous_city() -> None:
    """'london' must surface Heathrow, not London, Ontario."""
    results = search_airports("london", limit=3)

    assert results[0].iata == "LHR"


def test_search_matches_exact_iata_first() -> None:
    assert search_airports("ist", limit=1)[0].iata == "IST"


def test_search_can_be_scoped_to_one_country() -> None:
    results = search_airports("", limit=20, country="Jordan")

    assert results
    assert {airport.country for airport in results} == {"Jordan"}


def test_search_defaults_to_airports_with_real_service() -> None:
    results = search_airports("", limit=25)

    assert all(airport.is_scheduled for airport in results)


# ------------------------------------------------------------------- airlines


def test_carrier_codes_resolve_to_names() -> None:
    assert airline_name("TK") == "Turkish Airlines"
    assert airline_name("LH") == "Lufthansa"
    assert airline_name("RJ") == "Royal Jordanian"


def test_unknown_carrier_code_falls_back_to_the_code() -> None:
    assert airline_name("EB") == "EB"
    assert airline_name(None) == "Unknown"


def test_placeholder_airline_records_are_filtered_out() -> None:
    """The source has rows whose name is just the code echoed back ('ZZ' -> 'Zz')."""
    assert get_airline("ZZ") is None
    assert all(
        airline.name.casefold() != airline.iata.casefold() for airline in all_airlines()
    )


def test_airlines_with_numeric_iata_codes_are_included() -> None:
    """Codes like A3 and W6 are valid IATA and must not be filtered out."""
    assert get_airline("A3") is not None
    assert get_airline("W6") is not None


# --------------------------------------------------------------- route graph


def test_route_graph_knows_real_nonstop_service() -> None:
    assert has_route("AMM", "IST")
    assert "SKP" in onward_markets("IST")


def test_route_graph_rejects_invented_service() -> None:
    assert not has_route("AMM", "AKL")


def test_connecting_hubs_require_both_legs_to_exist() -> None:
    assert connects_via("AMM", "IST", "SKP")
    assert "IST" in one_stop_hubs("AMM", "SKP")


def test_countries_carry_iso_codes() -> None:
    jordan = get_country("JO")

    assert jordan is not None
    assert jordan.name == "Jordan"
    assert jordan.airport_count > 0


# ---------------------------------------------------------------- API layer


async def test_airports_endpoint_searches_globally(client: AsyncClient) -> None:
    results = (await client.get("/api/airports", params={"q": "kathmandu"})).json()

    assert results
    assert results[0]["iata"] == "KTM"
    assert results[0]["country"] == "Nepal"


async def test_airports_endpoint_supports_country_filter(client: AsyncClient) -> None:
    results = (
        await client.get("/api/airports", params={"q": "", "country": "JO", "limit": 20})
    ).json()

    assert results
    assert {airport["country"] for airport in results} == {"Jordan"}


async def test_airlines_endpoint_searches_by_name_and_code(client: AsyncClient) -> None:
    by_code = (await client.get("/api/airlines", params={"q": "TK"})).json()
    by_name = (await client.get("/api/airlines", params={"q": "turkish"})).json()

    assert by_code[0]["iata"] == "TK"
    assert by_code[0]["name"] == "Turkish Airlines"
    assert any(airline["iata"] == "TK" for airline in by_name)


async def test_airline_lookup_404s_for_an_unknown_code(client: AsyncClient) -> None:
    assert (await client.get("/api/airlines/EB")).status_code == 404


async def test_countries_endpoint_lists_every_country(client: AsyncClient) -> None:
    countries = (await client.get("/api/countries")).json()

    assert len(countries) > 200
    assert any(country["code"] == "JO" for country in countries)


async def test_coverage_endpoint_reports_dataset_size(client: AsyncClient) -> None:
    coverage = (await client.get("/api/coverage")).json()

    assert coverage["airports"] > 5000
    assert coverage["airlines"] > 1000
    assert coverage["countries"] > 200
    assert coverage["directed_routes"] > 30000


async def test_offers_name_the_operating_airline(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json={
                "origin": "AMM",
                "destination": "IST",
                "departure_date": (
                    __import__("datetime").date.today()
                    + __import__("datetime").timedelta(days=45)
                ).isoformat(),
            },
        )
    ).json()

    offer = body["baseline"]["offers"][0]
    assert offer["primary_carrier_name"]
    assert offer["primary_carrier_name"] != offer["primary_carrier"] or len(
        offer["primary_carrier"]
    ) == 2
    assert offer["itineraries"][0]["segments"][0]["carrier_name"]


async def test_search_reports_no_baggage_information(client: AsyncClient) -> None:
    """This app compares prices; bag allowances are deliberately out of scope."""
    body = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json={
                "origin": "AMM",
                "destination": "IST",
                "departure_date": (
                    __import__("datetime").date.today()
                    + __import__("datetime").timedelta(days=45)
                ).isoformat(),
            },
        )
    ).json()

    offer = body["baseline"]["offers"][0]
    assert "included_checked_bags" not in offer
    assert "deep_link" not in offer
