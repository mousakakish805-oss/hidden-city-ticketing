"""Search endpoints: queue a run, stream its progress, fetch the result."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import ProviderDep, SessionDep
from app.config import settings
from app.db.base import SessionLocal
from app.db.models import DisclaimerAcknowledgement
from app.providers.registry import get_provider
from app.schemas.search import (
    AcknowledgementIn,
    AcknowledgementOut,
    SearchCreatedOut,
    SearchRequestIn,
)
from app.services.events import event_bus
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])

# Strong references to in-flight runs; without this the event loop may garbage
# collect a task mid-run.
_running: set[asyncio.Task[Any]] = set()

SSE_KEEPALIVE_SECONDS = 15.0


async def _run_in_background(search_id: str, params: SearchRequestIn) -> None:
    """Execute a search on its own session, detached from the HTTP request.

    The request-scoped session is closed as soon as the response is sent, so a
    background run must open its own.
    """
    async with SessionLocal() as session:
        service = SearchService(session, get_provider())
        try:
            await service.run(search_id, params)
        except Exception:  # noqa: BLE001 - already recorded on the search row
            logger.warning("Background search %s ended in failure", search_id)


@router.post("", response_model=None, status_code=status.HTTP_202_ACCEPTED)
async def create_search(
    params: SearchRequestIn,
    session: SessionDep,
    provider: ProviderDep,
    response: Response,
    wait: bool = Query(
        default=False,
        description="Run synchronously and return the full result instead of a job handle.",
    ),
) -> dict[str, Any]:
    """Start a hidden-city search.

    Default is asynchronous: you get a ``search_id`` immediately and follow the
    batch engine live over SSE. Pass ``?wait=true`` for a single blocking call.
    """
    service = SearchService(session, provider)
    record = await service.create_search(params)
    search_id = record.id
    # Commit before handing off so the background task can see the row.
    await session.commit()

    if wait:
        response.status_code = status.HTTP_200_OK
        return await service.run(search_id, params)

    task = asyncio.create_task(_run_in_background(search_id, params))
    _running.add(task)
    task.add_done_callback(_running.discard)

    return SearchCreatedOut(
        search_id=search_id,
        status="pending",
        stream_url=f"{settings.api_prefix}/search/{search_id}/events",
        result_url=f"{settings.api_prefix}/search/{search_id}",
    ).model_dump()


@router.get("/{search_id}")
async def get_search(search_id: str, session: SessionDep) -> dict[str, Any]:
    """Fetch a finished result, or the current status if it is still running."""
    service = SearchService(session, get_provider())
    record = await service.get_search(search_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown search id")

    if record.status == "complete" and record.result:
        return record.result

    if record.status == "failed":
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=record.error or "The search failed upstream.",
        )

    return {
        "search_id": record.id,
        "status": record.status,
        "candidates_planned": record.candidates_planned,
        "candidates_probed": record.candidates_probed,
        "baseline_price": record.baseline_price,
    }


@router.get("/{search_id}/events")
async def stream_events(search_id: str, request: Request, session: SessionDep) -> StreamingResponse:
    """Server-sent events for one run's progress.

    Any backlog is replayed first, so connecting after the run started still
    shows the full story.
    """
    service = SearchService(session, get_provider())
    record = await service.get_search(search_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown search id")

    already_finished = record.status in {"complete", "failed"}

    async def event_stream() -> AsyncIterator[str]:
        queue, backlog = await event_bus.subscribe(search_id)
        try:
            for event in backlog:
                yield _format_sse(event)
            if already_finished and not backlog:
                yield _format_sse({"type": record.status, "search_id": search_id})
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                yield _format_sse(event)
                if event.get("type") in {"complete", "failed"}:
                    break
        finally:
            await event_bus.unsubscribe(search_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx buffering the stream into uselessness.
            "X-Accel-Buffering": "no",
        },
    )


def _format_sse(event: dict[str, Any]) -> str:
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"


@router.get("/{search_id}/matrix")
async def get_matrix(search_id: str, session: SessionDep) -> dict[str, Any]:
    """Just the comparative price matrix for a completed search."""
    service = SearchService(session, get_provider())
    record = await service.get_search(search_id)
    if record is None or not record.result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No completed search with that id")
    return {
        "search_id": search_id,
        "price_matrix": record.result.get("price_matrix", {}),
        "market_stats": record.result.get("market_stats", []),
    }


@router.post("/{search_id}/acknowledge", response_model=AcknowledgementOut)
async def acknowledge(
    search_id: str, body: AcknowledgementIn, request: Request, session: SessionDep
) -> AcknowledgementOut:
    """Record that the mandatory operational-risk warning was accepted.

    Kept server-side as an audit trail; the UI additionally gates rendering on
    it so hidden-city options are never shown before the rules are read.
    """
    if body.version != settings.disclaimer_version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Disclaimer version '{body.version}' is out of date "
                f"(current: '{settings.disclaimer_version}'). Re-read and re-accept."
            ),
        )

    record = DisclaimerAcknowledgement(
        client_token=body.client_token,
        version=body.version,
        search_id=search_id if search_id != "none" else None,
        user_agent=request.headers.get("user-agent", "")[:256] or None,
    )
    session.add(record)
    await session.flush()

    return AcknowledgementOut(
        acknowledged=True,
        version=body.version,
        acknowledged_at=datetime.now(UTC).isoformat(),
    )
