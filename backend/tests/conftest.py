"""Test configuration.

Environment is pinned *before* any application import, because
``app.config.settings`` is built once at import time and the database engine
binds to it immediately.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "hidden_city_test.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB.as_posix()}"
os.environ["FLIGHT_PROVIDER"] = "mock"
os.environ["MAX_CANDIDATE_DESTINATIONS"] = "6"
# Upstream pacing, not logic under test. At their real values (a 1 req/sec
# bucket and a 3s retry delay) these add over a minute to the suite.
os.environ["RAPIDAPI_POLL_DELAY_SECONDS"] = "0"
os.environ["RAPIDAPI_REQUESTS_PER_SECOND"] = "1000"

from collections.abc import AsyncIterator  # noqa: E402
from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.base import init_models  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.mock import MockFlightProvider  # noqa: E402


@pytest.fixture(scope="session")
def departure_date() -> date:
    return date.today() + timedelta(days=45)


@pytest.fixture
def provider() -> MockFlightProvider:
    return MockFlightProvider()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    await init_models()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
