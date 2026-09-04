"""Application configuration.

All tunables live here and are driven by environment variables (see
``.env.example``).  Nothing else in the codebase should read ``os.environ``
directly.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ProviderName = Literal["mock", "amadeus", "duffel", "rapidapi", "serpapi"]

# app/config.py -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Absolute, not relative: uvicorn is typically launched from the repository
# root while the file lives in backend/, and a relative path would silently
# find nothing -- leaving the app on the mock provider while .env clearly
# configures a real one.
#
# Tests never inherit a developer's local .env. Otherwise the suite behaves
# differently on a machine that has real credentials than in CI, and could make
# live, billable provider calls.
_ENV_FILE = None if os.environ.get("ENVIRONMENT") == "test" else str(BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- app ---
    app_name: str = "Hidden-City Ticketing"
    environment: Literal["dev", "prod", "test"] = "dev"
    debug: bool = True
    api_prefix: str = "/api"

    # CORS origins for the Vite dev server / deployed frontend.
    #
    # NoDecode is essential: without it pydantic-settings JSON-decodes any
    # list-typed field before validators run, so the natural
    # `CORS_ORIGINS=http://a,http://b` in .env would raise a JSONDecodeError
    # instead of reaching the comma-splitter below.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
        ]
    )

    # ----------------------------------------------------------- database ---
    # Postgres in production.  If this is left at the SQLite default the app
    # still runs end-to-end, which keeps local onboarding free of a DB install.
    database_url: str = "sqlite+aiosqlite:///./hidden_city.db"
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Create missing tables at startup. Convenient in development; turn OFF in
    # production and run ``alembic upgrade head`` instead, because create_all
    # cannot alter a table that already exists.
    auto_create_schema: bool = True

    # ----------------------------------------------------------- provider ---
    flight_provider: ProviderName = "mock"

    amadeus_client_id: str | None = None
    amadeus_client_secret: str | None = None
    amadeus_base_url: str = "https://test.api.amadeus.com"

    # Duffel uses one static bearer token. A `duffel_test_*` token returns
    # sandbox inventory; `duffel_live_*` hits real airlines.
    duffel_access_token: str | None = None
    duffel_base_url: str = "https://api.duffel.com"
    duffel_api_version: str = "v2"

    # SerpApi fronts Google Flights, so the fares are the published ones a
    # traveller would see -- there is no sandbox mode to fall into.
    serpapi_key: str | None = None
    serpapi_base_url: str = "https://serpapi.com"
    # `deep_search` makes SerpApi reproduce the Google Flights page exactly.
    #
    # On by default, and it should stay on. With it off, AMM->JED on
    # 2026-10-19 priced the 13:30 Saudia nonstop at $146; with it on, the same
    # flight is $131. A traveller who opens Google to check -- which this site
    # actively tells them to do -- finds the lower number and has no reason to
    # trust anything else on the page. Being slower is a much smaller problem
    # than being wrong by eleven percent.
    #
    # It costs no extra quota: still one search, just a slower one.
    serpapi_deep_search: bool = True

    # RapidAPI is a marketplace: one key, many APIs. The key authenticates you,
    # the host selects which listing you are calling, and each listing has its
    # own endpoints and response shape -- hence the separate host setting.
    rapidapi_key: str | None = None
    rapidapi_host: str | None = None

    # Skyscanner-derived listings return the first response as a *fragment*
    # and expect you to poll a session for the rest. Skipping the poll is not
    # a saving: a partial result set corrupts the baseline that every reported
    # saving is measured against. Each poll is one more API call.
    # One retry is enough in practice: an observed AMM->SKP search went from
    # empty to its full 8 itineraries on the first retry, and two further
    # retries added nothing. Raising this only helps on slow routes -- the
    # provider stops early once results stop growing.
    rapidapi_max_polls: int = 1
    # Multiplied by the attempt number, so waits grow: 3s, then 6s.
    rapidapi_poll_delay_seconds: float = 3.0

    # RapidAPI free tiers throttle hard -- typically around one request per
    # second, far below the global default. The provider uses its own bucket
    # rather than the shared one so a single slow marketplace plan does not
    # dictate the pace for every other provider.
    rapidapi_requests_per_second: float = 1.0

    # Duffel's sandbox injects a synthetic "Duffel Airways" (ZZ) nonstop into
    # every market, always priced below the real fares around it. Left in, it
    # becomes the baseline for every search and hides every genuine result.
    # Only applies to test tokens; live inventory has no ZZ.
    duffel_drop_test_airline: bool = True

    # -------------------------------------------------------- batch engine --
    # How many extended (A -> C) probes to fire for one user search.
    max_candidate_destinations: int = 12
    # Simultaneous in-flight provider requests.
    provider_concurrency: int = 6
    # Client-side rate limit so we stay inside provider quotas.
    provider_requests_per_second: float = 5.0
    provider_timeout_seconds: float = 25.0
    provider_max_retries: int = 2
    # Wall-clock budget for one complete batch run.
    batch_deadline_seconds: float = 90.0

    # -------------------------------------------------------- anomaly rules --
    # A hidden-city option must beat the baseline by BOTH thresholds to be
    # surfaced.  This suppresses noise from ordinary fare jitter.
    min_savings_absolute: float = 15.0
    min_savings_percent: float = 5.0
    # Reject "candidates" whose usable A->B portion arrives absurdly late.
    max_usable_duration_minutes: int = 60 * 30
    # Minimum ground time at B for the deplane to be operationally realistic.
    min_layover_minutes_at_target: int = 25

    # ------------------------------------------------------- geometry rules --
    # A candidate C is only plausible if B sits roughly *on the way* to C.
    # detour_ratio = (dist(A,B) + dist(B,C)) / dist(A,C); 1.0 == perfectly
    # collinear.  Anything above this is a backtrack, not an extension.
    max_detour_ratio: float = 1.45
    min_onward_leg_km: float = 150.0
    max_onward_leg_km: float = 4500.0

    # -------------------------------------------------------------- cache ---
    offer_cache_ttl_seconds: int = 60 * 30
    search_result_ttl_seconds: int = 60 * 60 * 6

    # --------------------------------------------------------------- redis ---
    # Required only to run more than one API worker: the SSE progress stream
    # has to reach a client connected to a different worker than the one
    # running the search. Unset means the in-process bus, which is correct for
    # a single worker.
    redis_url: str | None = None

    # --------------------------------------------------------- disclaimer ---
    # Bumping this invalidates every stored user acknowledgement.
    disclaimer_version: str = "2026.08.2"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def async_database_url(self) -> str:
        """Normalise a human-written URL to an asyncio driver.

        ``postgresql://...`` and ``postgres://...`` are what hosting providers
        hand out; SQLAlchemy's async engine needs an explicit async driver.

        A relative SQLite path is also anchored to the backend directory. Left
        relative it would resolve against the *working* directory, so running
        ``uvicorn`` from the repo root and ``alembic`` from ``backend/`` would
        quietly use two different database files.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        if url.startswith("sqlite://") and "+aiosqlite" not in url:
            url = "sqlite+aiosqlite://" + url[len("sqlite://") :]

        prefix = "sqlite+aiosqlite:///"
        if url.startswith(prefix):
            path = url[len(prefix) :]
            # ":memory:" and absolute paths are already unambiguous.
            if path.startswith("./") or (
                path and not Path(path).is_absolute() and path != ":memory:"
            ):
                resolved = (BACKEND_DIR / path.removeprefix("./")).resolve()
                url = f"{prefix}{resolved.as_posix()}"
        return url

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.async_database_url

    @property
    def amadeus_configured(self) -> bool:
        return bool(self.amadeus_client_id and self.amadeus_client_secret)

    @property
    def duffel_configured(self) -> bool:
        return bool(self.duffel_access_token)

    @property
    def rapidapi_configured(self) -> bool:
        return bool(self.rapidapi_key and self.rapidapi_host)

    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
