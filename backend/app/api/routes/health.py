"""Health, capability and disclaimer endpoints."""

from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

from app.api.deps import ProviderDep, SessionDep
from app.config import settings
from app.i18n import DEFAULT_LANGUAGE, is_rtl, normalize_language
from app.schemas.search import HealthOut
from app.services.disclaimer import disclaimer_payload

router = APIRouter(tags=["system"])

APP_VERSION = "1.0.0"


@router.get("/health", response_model=HealthOut)
async def health(session: SessionDep, provider: ProviderDep) -> HealthOut:
    """Liveness plus the two facts a client needs: which provider, and is the DB up."""
    database_reachable = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - the endpoint's job is to report this
        database_reachable = False

    provider_live = provider.name != "mock"

    # Metered providers publish what is left; surfacing it here means an
    # operator can see an exhausted plan before users hit failed searches.
    quota: int | None = None
    raw_quota = getattr(provider, "quota_remaining", None)
    if raw_quota is not None:
        with suppress(ValueError, TypeError):
            quota = int(raw_quota)

    return HealthOut(
        status="ok" if database_reachable else "degraded",
        provider=provider.name,
        provider_live=provider_live,
        provider_quota_remaining=quota,
        max_candidate_destinations=settings.max_candidate_destinations,
        database="postgresql" if settings.is_postgres else "sqlite",
        database_reachable=database_reachable,
        disclaimer_version=settings.disclaimer_version,
        version=APP_VERSION,
    )


@router.get("/disclaimer")
async def get_disclaimer(
    request: Request,
    lang: str | None = Query(
        default=None, description="'en' or 'ar'. Defaults to the Accept-Language header."
    ),
) -> dict:
    """Canonical, versioned warning text rendered by the mandatory modal."""
    language = normalize_language(lang or request.headers.get("accept-language"))
    return disclaimer_payload(language)


@router.get("/languages")
async def languages() -> dict:
    """Languages the API can render its own text in."""
    return {
        "default": DEFAULT_LANGUAGE,
        "languages": [
            {"code": code, "direction": "rtl" if is_rtl(code) else "ltr", "name": name}
            for code, name in (("en", "English"), ("ar", "العربية"))
        ],
    }
