"""What a visitor is allowed to see when a search fails.

The failure that prompted these tests reached a live browser reading:

    SearchFailed: Could not price the direct AMM->IST market: RapidAPI monthly
    quota is exhausted (0 requests remaining). Wait for the plan to reset, or
    upgrade it on the RapidAPI dashboard. Set FLIGHT_PROVIDER=mock to keep the
    app usable in the meantime.

Three separate faults in one sentence: an internal exception name, the vendor's
name, and an instruction to reconfigure a server the visitor does not run. The
operator still needs every word of it -- just not in the browser.
"""

from __future__ import annotations

import pytest

from app.i18n import SUPPORTED_LANGUAGES, translate
from app.providers.base import ProviderError
from app.services.errors import operator_detail, user_facing_message

# Anything here appearing in a visitor-facing string is a leak.
FORBIDDEN = (
    "rapidapi",
    "duffel",
    "amadeus",
    "serpapi",
    "google flights",
    "flight_provider",
    "searchfailed",
    "providererror",
    "traceback",
    "env",
    "http",
    "->",
)

# The real messages, verbatim, that this website has produced or can produce.
REAL_FAILURES = [
    ProviderError(
        "RapidAPI monthly quota is exhausted (0 requests remaining). Wait for "
        "the plan to reset, or upgrade it on the RapidAPI dashboard. Set "
        "FLIGHT_PROVIDER=mock to keep the app usable in the meantime."
    ),
    ProviderError("RapidAPI rate limited the request (HTTP 429)"),
    ProviderError("Duffel rejected the token: unauthorized"),
    ProviderError(
        "SerpApi plan is exhausted: You've ran out of searches for this month. "
        "Wait for the plan to reset, or upgrade it on the SerpApi dashboard."
    ),
    ProviderError("SerpApi rejected the api key (401). Check SERPAPI_KEY."),
    ProviderError("httpx transport error: connection timed out"),
    RuntimeError("No flights found for AMM->IST on 2026-09-01."),
    ValueError("something nobody predicted"),
]


@pytest.mark.parametrize("exc", REAL_FAILURES, ids=lambda e: type(e).__name__ + ":" + str(e)[:24])
@pytest.mark.parametrize("lang", sorted(SUPPORTED_LANGUAGES))
def test_visitor_message_leaks_nothing(exc: Exception, lang: str) -> None:
    message = user_facing_message(exc, lang).lower()

    assert message, "a visitor must always get something to read"
    for token in FORBIDDEN:
        assert token not in message, f"{token!r} leaked into the {lang} message: {message}"


def test_quota_exhaustion_tells_the_visitor_to_come_back() -> None:
    """The specific failure that was live on the website."""
    exc = ProviderError("RapidAPI monthly quota is exhausted (0 requests remaining).")

    assert user_facing_message(exc, "en") == translate("error.quota", "en")
    # Arabic visitors get Arabic, not an English fallback.
    assert user_facing_message(exc, "ar") == translate("error.quota", "ar")
    assert user_facing_message(exc, "ar") != user_facing_message(exc, "en")


def test_missing_flights_suggests_a_different_date() -> None:
    exc = RuntimeError("No flights found for AMM->IST on 2026-09-01.")
    assert user_facing_message(exc, "en") == translate("error.noFlights", "en")


def test_unknown_failures_fall_back_rather_than_echoing() -> None:
    """An unrecognised error must not be passed through verbatim."""
    exc = ValueError("KeyError: 'segments' at line 412 of parser.py")
    assert user_facing_message(exc, "en") == translate("error.unexpected", "en")


def test_operator_still_gets_the_whole_truth() -> None:
    """The technical text is not softened -- it is only redirected."""
    exc = ProviderError("RapidAPI monthly quota is exhausted (0 requests remaining).")
    detail = operator_detail(exc)

    assert detail.startswith("ProviderError:")
    assert "RapidAPI" in detail
    assert "0 requests remaining" in detail


@pytest.mark.parametrize("lang", sorted(SUPPORTED_LANGUAGES))
def test_every_error_key_is_translated(lang: str) -> None:
    for key in (
        "error.quota",
        "error.busy",
        "error.noFlights",
        "error.misconfigured",
        "error.unreachable",
        "error.unexpected",
    ):
        message = translate(key, lang)
        assert message != key, f"{key} is missing from the {lang} catalog"
        assert len(message) > 20, f"{key} in {lang} is too terse to help anyone"
