"""Concurrent fan-out engine for the extended A->C probes.

One user search becomes a dozen upstream searches.  This module owns the
concurrency, the per-probe isolation (one dead market must not sink the run)
and the overall wall-clock budget.

Deliberately free of database access: SQLAlchemy's ``AsyncSession`` is not safe
to share across concurrent tasks, so caching is handled sequentially by the
caller either side of the fan-out.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.providers.base import FlightProvider, Offer, ProviderError, SearchRequest

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class ProbeResult:
    """Outcome of a single origin/destination search."""

    request: SearchRequest
    offers: list[Offer] = field(default_factory=list)
    error: str | None = None
    from_cache: bool = False
    elapsed_ms: int = 0

    @property
    def destination(self) -> str:
        return self.request.destination

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def min_price(self) -> float | None:
        return min((offer.price_total for offer in self.offers), default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "offer_count": len(self.offers),
            "min_price": None if self.min_price is None else round(self.min_price, 2),
            "error": self.error,
            "from_cache": self.from_cache,
            "elapsed_ms": self.elapsed_ms,
        }


class BatchEngine:
    """Runs many provider searches concurrently under a shared budget."""

    def __init__(
        self,
        provider: FlightProvider,
        *,
        concurrency: int | None = None,
        deadline_seconds: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._provider = provider
        self._semaphore = asyncio.Semaphore(concurrency or settings.provider_concurrency)
        self._deadline = deadline_seconds or settings.batch_deadline_seconds
        self._on_progress = on_progress

    async def _emit(self, event: dict[str, Any]) -> None:
        if self._on_progress is None:
            return
        try:
            await self._on_progress(event)
        except Exception:  # pragma: no cover - progress must never break a run
            logger.debug("Progress callback failed", exc_info=True)

    async def probe(self, request: SearchRequest) -> ProbeResult:
        """Run one search, converting any failure into a recorded error."""
        started = time.perf_counter()
        await self._emit({"type": "probe_started", "destination": request.destination})

        async with self._semaphore:
            try:
                offers = await self._provider.search(request)
                result = ProbeResult(request=request, offers=list(offers))
            except ProviderError as exc:
                result = ProbeResult(request=request, error=str(exc))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad market must not abort the run
                logger.exception("Probe %s -> %s failed", request.origin, request.destination)
                result = ProbeResult(request=request, error=f"{type(exc).__name__}: {exc}")

        result.elapsed_ms = int((time.perf_counter() - started) * 1000)
        await self._emit({"type": "probe_finished", **result.to_dict()})
        return result

    async def probe_many(self, requests: Sequence[SearchRequest]) -> list[ProbeResult]:
        """Fan out every request, returning results in the input order.

        Probes still running when the wall-clock budget expires are cancelled
        and reported as timed out; whatever finished is still usable.
        """
        if not requests:
            return []

        tasks = [asyncio.create_task(self.probe(request)) for request in requests]
        try:
            async with asyncio.timeout(self._deadline):
                await asyncio.gather(*tasks, return_exceptions=True)
        except TimeoutError:
            logger.warning(
                "Batch deadline of %.1fs hit; %d/%d probes finished",
                self._deadline,
                sum(1 for task in tasks if task.done()),
                len(tasks),
            )
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        results: list[ProbeResult] = []
        for request, task in zip(requests, tasks, strict=True):
            if task.cancelled():
                results.append(ProbeResult(request=request, error="timed out"))
                continue
            exception = task.exception()
            if exception is not None:
                results.append(ProbeResult(request=request, error=str(exception)))
                continue
            results.append(task.result())
        return results


def flatten_offers(results: Sequence[ProbeResult]) -> list[Offer]:
    """Collect every offer from successful probes into one list."""
    return [offer for result in results if result.ok for offer in result.offers]
