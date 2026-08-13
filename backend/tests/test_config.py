"""Settings parsing.

These exist because a config bug does not fail in a test -- it fails at
startup, for a user following the setup guide, with a stack trace that points
at pydantic internals rather than at their .env file.
"""

from __future__ import annotations

import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The form the setup guide and .env.example both use.
        (
            "http://localhost:5173,http://127.0.0.1:5173",
            ["http://localhost:5173", "http://127.0.0.1:5173"],
        ),
        ("http://localhost:5173", ["http://localhost:5173"]),
        # Tolerate the spacing people naturally type.
        ("http://a.com , http://b.com", ["http://a.com", "http://b.com"]),
        ("http://a.com,,http://b.com", ["http://a.com", "http://b.com"]),
        ("", []),
    ],
)
def test_cors_origins_accepts_a_comma_separated_string(raw: str, expected: list[str]) -> None:
    """Without NoDecode, pydantic-settings JSON-decodes this first and blows up."""
    assert Settings(cors_origins=raw).cors_origins == expected


def test_cors_origins_still_accepts_a_real_list() -> None:
    origins = ["https://example.com"]

    assert Settings(cors_origins=origins).cors_origins == origins


def test_cors_origins_has_a_working_default() -> None:
    assert "http://localhost:5173" in Settings().cors_origins


# ------------------------------------------------------------ database URLs


@pytest.mark.parametrize(
    ("given", "expected_prefix"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://"),
        ("postgresql://u:p@h:5432/db", "postgresql+asyncpg://"),
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql+asyncpg://"),
    ],
)
def test_postgres_urls_are_upgraded_to_an_async_driver(
    given: str, expected_prefix: str
) -> None:
    assert Settings(database_url=given).async_database_url.startswith(expected_prefix)


def test_relative_sqlite_paths_are_anchored_to_the_backend_directory() -> None:
    """Otherwise uvicorn (run from the repo root) and alembic (run from
    backend/) would quietly use two different database files."""
    url = Settings(database_url="sqlite+aiosqlite:///./hidden_city.db").async_database_url

    assert "backend/hidden_city.db" in url.replace("\\", "/")


def test_absolute_sqlite_paths_are_left_alone() -> None:
    url = Settings(database_url="sqlite+aiosqlite:///C:/tmp/x.db").async_database_url

    assert url == "sqlite+aiosqlite:///C:/tmp/x.db"


def test_is_postgres_reflects_the_configured_engine() -> None:
    assert Settings(database_url="postgres://u:p@h/db").is_postgres
    assert not Settings(database_url="sqlite+aiosqlite:///./x.db").is_postgres


# ----------------------------------------------------------------- providers


def test_dotenv_path_is_absolute() -> None:
    """A relative path resolves against the *working* directory, so launching
    uvicorn from the repo root silently ignored backend/.env -- leaving the app
    on the mock provider while .env clearly configured a real one.

    Run in a subprocess from an unrelated directory: importing app.config with
    ENVIRONMENT unset in *this* process would rebuild the settings every other
    test shares.
    """
    import os
    import subprocess
    import sys
    import tempfile

    from app.config import BACKEND_DIR

    script = (
        "from pathlib import Path;"
        "from app.config import _ENV_FILE, BACKEND_DIR;"
        "p = Path(_ENV_FILE);"
        "assert p.is_absolute(), p;"
        "assert p.parent == BACKEND_DIR, p;"
        "print('ok')"
    )
    # Inherit the real environment (Windows needs SystemRoot to open sockets),
    # but drop ENVIRONMENT so the non-test branch is what gets exercised.
    child_env = {k: v for k, v in os.environ.items() if k != "ENVIRONMENT"}
    child_env["PYTHONPATH"] = str(BACKEND_DIR)

    result = subprocess.run(
        [sys.executable, "-c", script],
        # Deliberately not the backend directory: that is the whole point.
        cwd=tempfile.gettempdir(),
        env=child_env,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_tests_never_read_a_local_dotenv() -> None:
    """A developer with real credentials must run the same suite as CI --
    otherwise tests could quietly make live, billable provider calls."""
    from app.config import _ENV_FILE, settings

    assert _ENV_FILE is None
    assert settings.duffel_access_token is None
    assert settings.amadeus_client_id is None
    assert settings.flight_provider == "mock"


def test_provider_configuration_flags() -> None:
    assert not Settings(duffel_access_token=None).duffel_configured
    assert Settings(duffel_access_token="duffel_live_x").duffel_configured
    assert not Settings(amadeus_client_id="only-id").amadeus_configured
    assert Settings(amadeus_client_id="id", amadeus_client_secret="secret").amadeus_configured
