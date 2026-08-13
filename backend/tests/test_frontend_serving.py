"""How the app serves its two UIs.

Production ships the compiled React app at ``/`` and keeps the zero-build
preview at ``/preview``. A source checkout without a build has no compiled app,
so ``/`` falls back to the preview rather than 404ing.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.main import HAS_COMPILED_WEB, STATIC_DIR


async def test_preview_ui_is_always_available(client: AsyncClient) -> None:
    """The zero-build UI is what makes the backend demonstrable without Node."""
    response = await client.get("/preview")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # The preview compiles JSX in the browser; the built app does not.
    assert "babel" in response.text.lower()


async def test_root_serves_a_ui(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


async def test_root_prefers_the_compiled_app_when_present(client: AsyncClient) -> None:
    body = (await client.get("/")).text

    if HAS_COMPILED_WEB:
        # Vite emits hashed asset filenames.
        assert "/assets/index-" in body
        assert "babel" not in body.lower()
    else:
        # Falls back to the preview so a fresh checkout still works.
        assert "babel" in body.lower()


async def test_compiled_assets_are_served(client: AsyncClient) -> None:
    if not HAS_COMPILED_WEB:
        return

    import re

    match = re.search(r"/assets/(index-[\w]+\.js)", (await client.get("/")).text)
    assert match, "compiled index.html should reference a hashed JS bundle"

    response = await client.get(f"/assets/{match.group(1)}")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


async def test_api_still_wins_over_the_ui_routes(client: AsyncClient) -> None:
    """Mounting static files must not shadow the API."""
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_preview_ui_ships_with_the_package() -> None:
    assert (STATIC_DIR / "index.html").is_file()
