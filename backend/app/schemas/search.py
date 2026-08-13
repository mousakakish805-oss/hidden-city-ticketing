"""Request/response schemas for the public API."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.data.airports import get_airport
from app.i18n import DEFAULT_LANGUAGE, Language

CabinClass = Literal["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"]

IataCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")]


class SearchRequestIn(BaseModel):
    """A user's hidden-city search: origin A, desired destination B, date."""

    model_config = ConfigDict(str_strip_whitespace=True)

    origin: IataCode = Field(description="Departure airport, e.g. AMM")
    destination: IataCode = Field(description="Where you actually want to go, e.g. IST")
    departure_date: date
    return_date: date | None = Field(
        default=None,
        description=(
            "Set for a return trip. The two directions are priced as two "
            "SEPARATE one-way tickets, never as one round-trip fare -- skipping "
            "a leg on a round-trip ticket cancels everything after it, "
            "including your flight home. Doubles the number of API calls."
        ),
    )
    adults: int = Field(default=1, ge=1, le=9)
    cabin: CabinClass = "ECONOMY"
    currency: str = Field(default="USD", min_length=3, max_length=3)

    include_nearby_airports: bool = Field(
        default=False,
        description=(
            "Also accept deplaning at another airport in the same metro area "
            "(e.g. SAW when you asked for IST). Adds ground transfer."
        ),
    )
    lang: Language = Field(
        default=DEFAULT_LANGUAGE,
        description="Language for disclaimer text, risk warnings and booking guidance.",
    )
    max_candidates: int | None = Field(default=None, ge=1, le=40)
    min_savings_absolute: float | None = Field(default=None, ge=0)
    min_savings_percent: float | None = Field(default=None, ge=0, le=100)
    refresh: bool = Field(default=False, description="Bypass the offer cache.")

    @field_validator("origin", "destination", "currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("departure_date")
    @classmethod
    def _not_in_the_past(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("departure_date cannot be in the past")
        if value > date.today() + timedelta(days=365):
            raise ValueError("departure_date must be within the next 365 days")
        return value

    @property
    def is_round_trip(self) -> bool:
        return self.return_date is not None

    @model_validator(mode="after")
    def _validate_route(self) -> SearchRequestIn:
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        if self.return_date is not None:
            if self.return_date < self.departure_date:
                raise ValueError("return_date cannot be before departure_date")
            if self.return_date > date.today() + timedelta(days=365):
                raise ValueError("return_date must be within the next 365 days")
        # Candidate generation is coordinate-driven, so both endpoints must be
        # in the reference dataset.
        for field_name, code in (("origin", self.origin), ("destination", self.destination)):
            if get_airport(code) is None:
                raise ValueError(
                    f"{field_name} '{code}' is not in the airport reference data. "
                    "See GET /api/airports for supported codes."
                )
        return self


class SearchCreatedOut(BaseModel):
    """Returned immediately when a search is queued."""

    search_id: str
    status: Literal["pending", "running", "complete", "failed"]
    stream_url: str
    result_url: str


class AirportOut(BaseModel):
    iata: str
    name: str
    city: str
    country: str
    country_code: str | None
    region: str
    lat: float
    lon: float
    hub_tier: int
    destination_count: int
    carrier_count: int
    label: str


class AirlineOut(BaseModel):
    iata: str
    name: str
    country: str
    active: bool
    icao: str | None
    booking_url: str | None
    label: str


class CountryOut(BaseModel):
    name: str
    code: str | None
    region: str
    airport_count: int


class AcknowledgementIn(BaseModel):
    client_token: str = Field(min_length=8, max_length=64)
    version: str = Field(min_length=1, max_length=16)
    search_id: str | None = Field(default=None, max_length=32)
    accepted_codes: list[str] = Field(default_factory=list)


class AcknowledgementOut(BaseModel):
    acknowledged: bool
    version: str
    acknowledged_at: str


class TrendPointOut(BaseModel):
    observed_at: str
    min_price: float
    median_price: float | None
    offer_count: int


class TrendOut(BaseModel):
    origin: str
    destination: str
    currency: str
    points: list[TrendPointOut]
    latest: float | None
    lowest: float | None
    highest: float | None
    average: float | None
    change_percent: float | None


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    provider: str
    provider_live: bool
    # Requests left on a metered plan, as last reported by the provider.
    # None means the provider does not publish one (or has not been called yet).
    provider_quota_remaining: int | None = None
    database: str
    database_reachable: bool
    disclaimer_version: str
    version: str


# The search result itself is assembled by the service layer as a plain dict --
# it is deeply nested and mirrors what the UI renders one-to-one, so a second
# model definition would only add drift. This alias documents that intent.
SearchResult = dict[str, Any]
