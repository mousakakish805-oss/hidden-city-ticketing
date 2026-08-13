"""Localisation: catalog integrity, language negotiation, and booking links."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.data.airline_sites import AIRLINE_SITES
from app.data.airlines import airline_booking_url, get_airline
from app.i18n import (
    SUPPORTED_LANGUAGES,
    is_rtl,
    missing_keys,
    normalize_language,
    translate,
)
from app.i18n.catalog_en import MESSAGES_EN

DEPART = (date.today() + timedelta(days=45)).isoformat()

PLACEHOLDER = re.compile(r"\{(\w+)\}")


# ------------------------------------------------------------ catalog health


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_every_language_covers_every_key(lang: str) -> None:
    """A missing key silently falls back to English, so catch drift here."""
    assert missing_keys(lang) == set()


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_placeholders_match_across_languages(lang: str) -> None:
    """A translation that drops or renames a placeholder would render wrongly."""
    from app.i18n import CATALOGS

    for key, english in MESSAGES_EN.items():
        translated = CATALOGS[lang][key]
        assert set(PLACEHOLDER.findall(english)) == set(PLACEHOLDER.findall(translated)), (
            f"placeholder mismatch in '{key}' for language '{lang}'"
        )


def test_arabic_catalog_is_actually_arabic() -> None:
    from app.i18n.catalog_ar import MESSAGES_AR

    arabic_range = re.compile(r"[؀-ۿ]")
    for key, text in MESSAGES_AR.items():
        assert arabic_range.search(text), f"'{key}' has no Arabic characters"


# ------------------------------------------------------ language negotiation


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("ar", "ar"),
        ("AR", "ar"),
        ("ar-JO", "ar"),
        ("ar_SA", "ar"),
        ("ar-JO,ar;q=0.9,en;q=0.8", "ar"),
        ("en-GB", "en"),
        ("fr-FR,fr;q=0.9", "en"),  # unsupported falls back
        ("", "en"),
        (None, "en"),
    ],
)
def test_language_negotiation(header: str | None, expected: str) -> None:
    assert normalize_language(header) == expected


def test_arabic_is_right_to_left() -> None:
    assert is_rtl("ar") is True
    assert is_rtl("en") is False


def test_unknown_key_degrades_instead_of_raising() -> None:
    assert translate("no.such.key", "ar") == "no.such.key"


def test_missing_parameter_degrades_instead_of_raising() -> None:
    result = translate("risk.CARRY_ON_ONLY", "en")
    assert "{ticketed_city}" in result  # unformatted, but not an exception


# ---------------------------------------------------------------- booking


def test_major_carriers_have_a_booking_site() -> None:
    for code in ("TK", "RJ", "LH", "EK", "QR", "MS", "BA", "AF"):
        assert airline_booking_url(code), f"{code} should have a booking site"


def test_booking_sites_are_plausible_https_urls() -> None:
    for code, url in AIRLINE_SITES.items():
        assert url.startswith("https://"), f"{code} url is not https"
        assert " " not in url
        assert not url.endswith("/"), f"{code} url has a trailing slash"


def test_unknown_carrier_has_no_booking_site() -> None:
    assert airline_booking_url("EB") is None
    assert airline_booking_url(None) is None


def test_booking_url_is_exposed_on_the_airline_record() -> None:
    turkish = get_airline("TK")
    assert turkish is not None
    assert turkish.booking_url == "https://www.turkishairlines.com"


# -------------------------------------------------------------- API surface


async def test_disclaimer_is_served_in_arabic(client: AsyncClient) -> None:
    arabic = (await client.get("/api/disclaimer", params={"lang": "ar"})).json()
    english = (await client.get("/api/disclaimer", params={"lang": "en"})).json()

    assert arabic["language"] == "ar"
    assert arabic["title"] != english["title"]
    # Structure must be identical -- only the prose changes.
    assert [r["code"] for r in arabic["rules"]] == [r["code"] for r in english["rules"]]
    assert arabic["required_codes"] == english["required_codes"]
    assert arabic["version"] == english["version"]


async def test_disclaimer_honours_the_accept_language_header(client: AsyncClient) -> None:
    response = await client.get("/api/disclaimer", headers={"Accept-Language": "ar-JO,ar;q=0.9"})

    assert response.json()["language"] == "ar"


async def test_disclaimer_covers_the_risks_travellers_actually_hit(
    client: AsyncClient,
) -> None:
    """Each of these has cost real travellers real money. A gap here is not a
    documentation problem -- it is the one thing this website owes its users."""
    rules = (await client.get("/api/disclaimer")).json()["rules"]
    codes = {rule["code"] for rule in rules}

    assert {
        "ONE_WAY_ONLY",          # loses your flight home
        "CARRY_ON_ONLY",         # loses your luggage
        "CONTRACT_OF_CARRIAGE",  # fare-difference invoices, account closure
        "REROUTE_RISK",          # lands you in the wrong city
        "IMMIGRATION",           # refused entry where you get off
        "NO_LOYALTY_NUMBER",     # how airlines link repeat offenders
        "TRAVEL_INSURANCE",      # claims denied after a deliberate breach
        "NO_CHANGES",            # cancelling the leg re-prices the ticket
        "PASSENGER_RIGHTS",      # forfeited delay/cancellation compensation
        "NOT_ADVICE",
    } <= codes


async def test_every_rule_explains_the_consequence_not_just_the_instruction(
    client: AsyncClient,
) -> None:
    """A rule that says only 'do not do X' teaches nothing. Each body must be
    substantial enough to explain why."""
    for rule in (await client.get("/api/disclaimer")).json()["rules"]:
        assert rule["title"], rule["code"]
        assert len(rule["body"]) > 120, f"{rule['code']} body is too thin to explain itself"


async def test_languages_endpoint_lists_both(client: AsyncClient) -> None:
    body = (await client.get("/api/languages")).json()

    codes = {entry["code"]: entry for entry in body["languages"]}
    assert set(codes) == {"en", "ar"}
    assert codes["ar"]["direction"] == "rtl"
    assert codes["en"]["direction"] == "ltr"


async def test_search_returns_arabic_risk_messages(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json={
                "origin": "AMM",
                "destination": "IST",
                "departure_date": DEPART,
                "lang": "ar",
            },
        )
    ).json()

    assert body["language"] == "ar"
    assert body["direction"] == "rtl"
    assert body["hidden_city"]["count"] > 0

    option = body["hidden_city"]["options"][0]
    arabic_range = re.compile(r"[؀-ۿ]")
    assert arabic_range.search(option["risk"]["flags"][0]["message"])
    assert arabic_range.search(body["disclaimer"]["summary"])


async def test_search_defaults_to_english(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json={"origin": "AMM", "destination": "IST", "departure_date": DEPART},
        )
    ).json()

    assert body["language"] == "en"
    assert body["direction"] == "ltr"


async def test_prices_and_confidence_do_not_change_with_language(client: AsyncClient) -> None:
    """Language must affect presentation only, never the analysis."""
    payload = {"origin": "AMM", "destination": "IST", "departure_date": DEPART}
    english = (
        await client.post("/api/search", params={"wait": "true"}, json=payload)
    ).json()
    arabic = (
        await client.post("/api/search", params={"wait": "true"}, json={**payload, "lang": "ar"})
    ).json()

    assert english["baseline"]["price"] == arabic["baseline"]["price"]
    assert english["hidden_city"]["count"] == arabic["hidden_city"]["count"]
    assert [o["price"] for o in english["hidden_city"]["options"]] == [
        o["price"] for o in arabic["hidden_city"]["options"]
    ]
    assert [o["risk"]["confidence"] for o in english["hidden_city"]["options"]] == [
        o["risk"]["confidence"] for o in arabic["hidden_city"]["options"]
    ]


async def test_every_option_carries_booking_guidance(client: AsyncClient) -> None:
    body = (
        await client.post(
            "/api/search",
            params={"wait": "true"},
            json={"origin": "AMM", "destination": "IST", "departure_date": DEPART},
        )
    ).json()

    for option in body["hidden_city"]["options"]:
        booking = option["booking"]
        assert booking["carrier_name"]
        # Tells the user exactly what to search on the airline's own site.
        assert option["ticketed_iata"] in booking["instructions"]
        assert option["deplane_iata"] in booking["instructions"]
        # Either a real link, or an explicit note that we have none.
        assert booking["url"] or booking["note"]
        if booking["url"]:
            assert booking["url"].startswith("https://")


async def test_invalid_language_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/search",
        params={"wait": "true"},
        json={
            "origin": "AMM",
            "destination": "IST",
            "departure_date": DEPART,
            "lang": "klingon",
        },
    )

    assert response.status_code == 422
