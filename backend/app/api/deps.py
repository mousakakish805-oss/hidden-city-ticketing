"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.providers.base import FlightProvider
from app.providers.registry import get_provider

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ProviderDep = Annotated[FlightProvider, Depends(get_provider)]
