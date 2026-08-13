"""The served-route graph: which airports connect to where, and on which airline.

Replaces the hand-written onward-market map this project started with. For any
hub B anywhere in the world, ``onward_markets(B)`` returns destinations that
genuinely have nonstop service, so the batch engine only spends API calls on
routings that can physically exist.

Coverage caveat: this is a published snapshot, not a live schedule feed, so it
lags reality -- a route that closed since the snapshot may still appear. That
is safe by construction: the graph only decides *what to price*, and the flight
provider decides what actually exists. A stale market simply returns no offers.
"""

from __future__ import annotations

from functools import lru_cache

from app.data._store import load


@lru_cache(maxsize=1)
def _graph() -> dict[str, dict[str, tuple[str, ...]]]:
    """``{origin: {destination: (operating airline codes, ...)}}``."""
    return {
        origin: {dest: tuple(operators) for dest, operators in destinations.items()}
        for origin, destinations in load("routes").items()
    }


@lru_cache(maxsize=1)
def _reverse_graph() -> dict[str, tuple[str, ...]]:
    incoming: dict[str, list[str]] = {}
    for origin, destinations in _graph().items():
        for destination in destinations:
            incoming.setdefault(destination, []).append(origin)
    return {code: tuple(sorted(origins)) for code, origins in incoming.items()}


def onward_markets(hub_iata: str) -> tuple[str, ...]:
    """Destinations with known nonstop service from ``hub_iata``."""
    return tuple(_graph().get(hub_iata.strip().upper(), {}))


def inbound_markets(hub_iata: str) -> tuple[str, ...]:
    """Origins with known nonstop service *to* ``hub_iata``."""
    return _reverse_graph().get(hub_iata.strip().upper(), ())


def has_route(origin: str, destination: str) -> bool:
    return destination.strip().upper() in _graph().get(origin.strip().upper(), {})


def route_operators(origin: str, destination: str) -> tuple[str, ...]:
    """Active airlines known to fly this exact leg, busiest hub first."""
    return _graph().get(origin.strip().upper(), {}).get(destination.strip().upper(), ())


def connects_via(origin: str, hub: str, destination: str) -> bool:
    """Whether ``origin -> hub -> destination`` is a physically served routing."""
    return has_route(origin, hub) and has_route(hub, destination)


def one_stop_hubs(origin: str, destination: str) -> tuple[str, ...]:
    """Every airport that could host a single connection between two points."""
    origin, destination = origin.strip().upper(), destination.strip().upper()
    outbound = set(onward_markets(origin))
    inbound = set(inbound_markets(destination))
    return tuple(sorted((outbound & inbound) - {origin, destination}))


def common_operator(legs: list[tuple[str, str]]) -> str | None:
    """An airline that flies every leg, or ``None`` if no single carrier does.

    Real connecting itineraries are usually sold on one carrier, so this is
    what makes a synthesised multi-leg trip look like something a GDS would
    actually return.
    """
    shared: set[str] | None = None
    for origin, destination in legs:
        operators = set(route_operators(origin, destination))
        shared = operators if shared is None else (shared & operators)
        if not shared:
            return None
    return sorted(shared)[0] if shared else None


def route_count(iata: str) -> int:
    return len(onward_markets(iata))
