"""Async SQLAlchemy engine, session factory and declarative base."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _engine_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"echo": settings.db_echo, "future": True}
    # SQLite's aiosqlite driver rejects pool sizing arguments.
    if settings.is_postgres:
        kwargs |= {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_pre_ping": True,
        }
    return kwargs


engine: AsyncEngine = create_async_engine(settings.async_database_url, **_engine_kwargs())

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Create any missing tables, for development and tests only.

    Production runs Alembic instead (``alembic upgrade head``), which is the
    only way to evolve a schema that already holds data. ``create_all`` adds
    missing tables but never alters existing ones, so a column added later
    would silently not appear -- hence the guard below.
    """
    if not settings.auto_create_schema:
        logger.info("auto_create_schema is off; run 'alembic upgrade head' to migrate.")
        return

    # Imported for the side effect of registering models on ``Base.metadata``.
    from app.db import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    await engine.dispose()
