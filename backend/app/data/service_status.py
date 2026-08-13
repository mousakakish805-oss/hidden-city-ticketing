"""Airports where scheduled civil service has stopped since the route snapshot.

The bundled route graph is a published dump from around 2014. Aviation has
moved on, and the gaps are not random -- they cluster around conflict. Proposing
Donetsk as a destination is not a small cosmetic error: that airport was
destroyed in 2014, and offering it makes correct output look broken.

Two mechanisms cover this, and both are needed:

* **This list** handles the first search, before the app has learned anything.
  It is small, curated, and dated on purpose -- see the review note below.
* **Learned suppression** (``RouteCandidate.times_empty`` in ``core/hub_graph``)
  handles everything else. A market that repeatedly returns no offers stops
  being probed, whatever the reason and without anyone maintaining a list.

Entries are *suppressed as candidates* only. Nothing here blocks a user from
searching an airport directly -- if they ask for it, they get an honest answer
from the provider.

REVIEW BY: 2027-01-01. Suspensions end as well as begin; a stale block-list is
its own bug. Verify against a current source before extending it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.data.airports import all_airports


@dataclass(frozen=True, slots=True)
class Suspension:
    reason: str
    since: str


# Whole countries whose airspace is closed to scheduled civil aviation.
SUSPENDED_COUNTRIES: dict[str, Suspension] = {
    "Ukraine": Suspension("Airspace closed to civil aviation", "2022-02"),
    "Sudan": Suspension("Airspace closed to civil aviation", "2023-04"),
}

# Individual airports closed while the rest of the country still flies.
SUSPENDED_AIRPORTS: dict[str, Suspension] = {
    "DOK": Suspension("Donetsk airport destroyed", "2014-05"),
    "VSG": Suspension("Luhansk airport destroyed", "2014-06"),
    "SIP": Suspension("Simferopol closed to international traffic", "2014-04"),
    "SAH": Suspension("Sanaa closed to most scheduled service", "2016-08"),
    "HOD": Suspension("Hodeidah closed to scheduled service", "2016-08"),
    # Southern and western Russian airports inside the closed airspace zone.
    # The rest of Russia still operates, so this cannot be a country-wide rule.
    "ROV": Suspension("Rostov-on-Don inside closed airspace zone", "2022-02"),
    "KRR": Suspension("Krasnodar inside closed airspace zone", "2022-02"),
    "AAQ": Suspension("Anapa inside closed airspace zone", "2022-02"),
    "GDZ": Suspension("Gelendzhik inside closed airspace zone", "2022-02"),
    "EGO": Suspension("Belgorod inside closed airspace zone", "2022-02"),
    "URS": Suspension("Kursk inside closed airspace zone", "2022-02"),
    "VOZ": Suspension("Voronezh inside closed airspace zone", "2022-02"),
    "BZK": Suspension("Bryansk inside closed airspace zone", "2022-02"),
    "LPK": Suspension("Lipetsk inside closed airspace zone", "2022-02"),
    "ESL": Suspension("Elista inside closed airspace zone", "2022-02"),
}


@lru_cache(maxsize=1)
def _suspended_index() -> dict[str, Suspension]:
    """Every suspended airport code, country rules expanded to their airports."""
    index: dict[str, Suspension] = dict(SUSPENDED_AIRPORTS)
    if SUSPENDED_COUNTRIES:
        for airport in all_airports():
            suspension = SUSPENDED_COUNTRIES.get(airport.country)
            if suspension is not None:
                index.setdefault(airport.iata, suspension)
    return index


def is_suspended(iata: str) -> bool:
    return iata.strip().upper() in _suspended_index()


def suspension_for(iata: str) -> Suspension | None:
    return _suspended_index().get(iata.strip().upper())


def suspended_codes() -> frozenset[str]:
    return frozenset(_suspended_index())
