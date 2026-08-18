"""Provider selection and lifecycle.

One process-wide provider instance is reused so HTTP connection pools and
OAuth tokens survive between requests.
"""

from __future__ import annotations

import logging

from app.config import ProviderName, settings
from app.providers.base import FlightProvider, ProviderError
from app.providers.mock import MockFlightProvider

logger = logging.getLogger(__name__)

_provider: FlightProvider | None = None


def _build_amadeus() -> FlightProvider:
    if not settings.amadeus_configured:
        logger.warning(
            "FLIGHT_PROVIDER=amadeus but credentials are missing; "
            "falling back to the mock provider."
        )
        return MockFlightProvider()

    # Imported lazily so one provider's dependencies can never break another.
    from app.providers.amadeus import AmadeusProvider

    return AmadeusProvider()


def _build_duffel() -> FlightProvider:
    if not settings.duffel_configured:
        logger.warning(
            "FLIGHT_PROVIDER=duffel but DUFFEL_ACCESS_TOKEN is missing; "
            "falling back to the mock provider."
        )
        return MockFlightProvider()

    from app.providers.duffel import DuffelProvider

    provider = DuffelProvider()
    if not provider.is_live_mode:
        logger.warning(
            "Duffel token is a TEST token: offers come from Duffel's sandbox "
            "airline, not real airline inventory. Use a duffel_live_* token "
            "for real fares."
        )
    return provider


def _build_rapidapi() -> FlightProvider:
    if not settings.rapidapi_configured:
        logger.warning(
            "FLIGHT_PROVIDER=rapidapi but RAPIDAPI_KEY/RAPIDAPI_HOST are missing; "
            "falling back to the mock provider."
        )
        return MockFlightProvider()

    from app.providers.rapidapi import RapidApiProvider

    provider = RapidApiProvider()
    # Worth saying out loud on a metered plan: one user search fans out to
    # roughly this many upstream calls.
    logger.info(
        "RapidAPI host=%s | ~%d calls per search (1 baseline + %d candidates)",
        settings.rapidapi_host,
        settings.max_candidate_destinations + 1,
        settings.max_candidate_destinations,
    )
    return provider


def _build_serpapi() -> FlightProvider:
    if not settings.serpapi_configured:
        logger.warning(
            "FLIGHT_PROVIDER=serpapi but SERPAPI_KEY is missing; falling back to the mock provider."
        )
        return MockFlightProvider()

    from app.providers.serpapi import SerpApiProvider

    provider = SerpApiProvider()
    # One call per market, with no retry tax: SerpApi returns a complete
    # result first time, unlike listings that answer with a fragment.
    logger.info(
        "SerpApi ready | ~%d searches per user query (1 baseline + %d candidates)",
        settings.max_candidate_destinations + 1,
        settings.max_candidate_destinations,
    )
    return provider


BUILDERS = {
    "amadeus": _build_amadeus,
    "duffel": _build_duffel,
    "rapidapi": _build_rapidapi,
    "serpapi": _build_serpapi,
}


def build_provider(name: ProviderName | None = None) -> FlightProvider:
    """Instantiate a provider by name, falling back to the mock when unusable."""
    chosen = name or settings.flight_provider
    builder = BUILDERS.get(chosen)
    if builder is None:
        return MockFlightProvider()

    try:
        return builder()
    except ProviderError as exc:
        logger.warning("Provider %r unavailable (%s); using mock.", chosen, exc)
        return MockFlightProvider()


def get_provider() -> FlightProvider:
    global _provider
    if _provider is None:
        _provider = build_provider()
        logger.info("Flight provider initialised: %s", _provider.name)
    return _provider


def set_provider(provider: FlightProvider | None) -> None:
    """Override the active provider (used by tests)."""
    global _provider
    _provider = provider


async def close_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.aclose()
        _provider = None
