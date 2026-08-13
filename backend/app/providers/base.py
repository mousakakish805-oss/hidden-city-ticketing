"""Provider-agnostic flight model and the search interface.

Every provider normalises into these dataclasses, so the analysis layer never
sees a vendor-specific payload.  Adding a new source (Duffel, Kiwi, an internal
GDS feed) means implementing ``FlightProvider`` and nothing else.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from app.data.airlines import airline_name

_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso_duration(value: str | None) -> int:
    """Convert an ISO-8601 duration such as ``PT4H35M`` to whole minutes."""
    if not value:
        return 0
    match = _ISO_DURATION.match(value.strip().upper())
    if not match:
        return 0
    parts = {key: int(val) for key, val in match.groupdict(default="0").items()}
    return parts["days"] * 1440 + parts["hours"] * 60 + parts["minutes"] + parts["seconds"] // 60


def format_minutes(total_minutes: int) -> str:
    """``265`` -> ``'4h 25m'``."""
    hours, minutes = divmod(max(int(total_minutes), 0), 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


class ProviderError(RuntimeError):
    """Raised when an upstream flight source fails in a non-recoverable way."""


@dataclass(frozen=True, slots=True)
class Segment:
    """A single flight leg operated under one flight number."""

    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    carrier: str
    flight_number: str
    duration_minutes: int
    aircraft: str | None = None
    operating_carrier: str | None = None
    cabin: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "departure_at": self.departure_at.isoformat(),
            "arrival_at": self.arrival_at.isoformat(),
            "carrier": self.carrier,
            "carrier_name": airline_name(self.carrier),
            "flight_number": self.flight_number,
            "duration_minutes": self.duration_minutes,
            "duration_label": format_minutes(self.duration_minutes),
            "aircraft": self.aircraft,
            "operating_carrier": self.operating_carrier,
            "cabin": self.cabin,
        }


@dataclass(frozen=True, slots=True)
class Itinerary:
    """An ordered chain of segments forming one directional journey."""

    segments: tuple[Segment, ...]
    duration_minutes: int

    @property
    def origin(self) -> str:
        return self.segments[0].origin

    @property
    def destination(self) -> str:
        return self.segments[-1].destination

    @property
    def stop_count(self) -> int:
        return max(len(self.segments) - 1, 0)

    @property
    def path(self) -> tuple[str, ...]:
        """Full airport chain, e.g. ``('AMM', 'IST', 'SKP')``."""
        return (self.segments[0].origin, *(s.destination for s in self.segments))

    def layover_minutes_after(self, segment_index: int) -> int | None:
        """Ground time between segment ``segment_index`` and the next one."""
        if segment_index < 0 or segment_index >= len(self.segments) - 1:
            return None
        arrival = self.segments[segment_index].arrival_at
        departure = self.segments[segment_index + 1].departure_at
        return max(int((departure - arrival).total_seconds() // 60), 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": [segment.to_dict() for segment in self.segments],
            "duration_minutes": self.duration_minutes,
            "duration_label": format_minutes(self.duration_minutes),
            "stop_count": self.stop_count,
            "path": list(self.path),
        }


@dataclass(frozen=True, slots=True)
class Offer:
    """A bookable, priced itinerary as returned by a provider."""

    provider: str
    offer_id: str
    search_origin: str
    search_destination: str
    departure_date: date
    price_total: float
    currency: str
    itineraries: tuple[Itinerary, ...]
    validating_carriers: tuple[str, ...] = ()
    cabin: str = "ECONOMY"
    # Kept because a thin fare bucket signals the price is about to move --
    # this app reports prices, not baggage allowances or booking availability.
    bookable_seats: int | None = None
    raw: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    @property
    def outbound(self) -> Itinerary:
        return self.itineraries[0]

    @property
    def primary_carrier(self) -> str:
        if self.validating_carriers:
            return self.validating_carriers[0]
        return self.outbound.segments[0].carrier

    @property
    def primary_carrier_name(self) -> str:
        return airline_name(self.primary_carrier)

    @property
    def is_one_way(self) -> bool:
        return len(self.itineraries) == 1

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "offer_id": self.offer_id,
            "search_origin": self.search_origin,
            "search_destination": self.search_destination,
            "departure_date": self.departure_date.isoformat(),
            "price_total": round(self.price_total, 2),
            "currency": self.currency,
            "itineraries": [it.to_dict() for it in self.itineraries],
            "validating_carriers": list(self.validating_carriers),
            "cabin": self.cabin,
            "bookable_seats": self.bookable_seats,
            "primary_carrier": self.primary_carrier,
            "primary_carrier_name": self.primary_carrier_name,
            "stop_count": self.outbound.stop_count,
            "duration_minutes": self.outbound.duration_minutes,
            "duration_label": format_minutes(self.outbound.duration_minutes),
        }
        if include_raw:
            payload["raw"] = self.raw
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Offer:
        """Rehydrate an offer previously persisted by :meth:`to_dict`."""
        itineraries = tuple(
            Itinerary(
                segments=tuple(
                    Segment(
                        origin=seg["origin"],
                        destination=seg["destination"],
                        departure_at=datetime.fromisoformat(seg["departure_at"]),
                        arrival_at=datetime.fromisoformat(seg["arrival_at"]),
                        carrier=seg["carrier"],
                        flight_number=seg["flight_number"],
                        duration_minutes=seg["duration_minutes"],
                        aircraft=seg.get("aircraft"),
                        operating_carrier=seg.get("operating_carrier"),
                        cabin=seg.get("cabin"),
                    )
                    for seg in itinerary["segments"]
                ),
                duration_minutes=itinerary["duration_minutes"],
            )
            for itinerary in payload["itineraries"]
        )
        return cls(
            provider=payload["provider"],
            offer_id=payload["offer_id"],
            search_origin=payload["search_origin"],
            search_destination=payload["search_destination"],
            departure_date=date.fromisoformat(payload["departure_date"]),
            price_total=float(payload["price_total"]),
            currency=payload["currency"],
            itineraries=itineraries,
            validating_carriers=tuple(payload.get("validating_carriers") or ()),
            cabin=payload.get("cabin", "ECONOMY"),
            bookable_seats=payload.get("bookable_seats"),
        )


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Normalised parameters for a single origin/destination probe."""

    origin: str
    destination: str
    departure_date: date
    adults: int = 1
    cabin: str = "ECONOMY"
    currency: str = "USD"
    max_results: int = 30
    non_stop: bool = False

    def cache_key(self, provider: str) -> tuple[str, str, str, str, str, int]:
        return (
            provider,
            self.origin,
            self.destination,
            self.departure_date.isoformat(),
            self.cabin,
            self.adults,
        )

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["departure_date"] = self.departure_date.isoformat()
        return data


@runtime_checkable
class FlightProvider(Protocol):
    """The single seam between this app and any upstream flight source."""

    name: str

    async def search(self, request: SearchRequest) -> list[Offer]:
        """Return priced one-way offers for ``request``.

        Implementations should raise :class:`ProviderError` on unrecoverable
        upstream failures and return ``[]`` when a market simply has no
        availability -- the batch engine treats those cases differently.
        """
        ...

    async def aclose(self) -> None:
        """Release network resources."""
        ...
