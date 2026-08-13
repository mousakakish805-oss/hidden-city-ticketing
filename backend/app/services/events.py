"""Pub/sub for live batch-run progress.

Two backends behind one interface:

* **In-process** (default) -- zero dependencies, correct for a single worker.
* **Redis** -- used automatically when ``REDIS_URL`` is set.

The distinction matters as soon as you run more than one API worker. A search
runs on whichever worker accepted the POST, but the browser's SSE connection
can land on a different one; with an in-process bus that client would sit and
watch nothing happen. Redis makes the stream worker-independent.

Both backends replay history to late subscribers, so a client that connects
after a run started still sees the whole story rather than joining mid-way.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Bounded so a disconnected client cannot grow memory without limit.
QUEUE_MAXSIZE = 256

# History is only needed while a run is in flight; an hour is generous.
HISTORY_TTL_SECONDS = 3600


class EventBus(ABC):
    """Fan-out of per-search event streams to any number of subscribers."""

    @abstractmethod
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...

    @abstractmethod
    async def subscribe(
        self, topic: str
    ) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        """Register a listener, returning its queue plus the backlog so far."""

    @abstractmethod
    async def unsubscribe(self, topic: str, queue: asyncio.Queue[dict[str, Any]]) -> None: ...

    async def clear(self, topic: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


class InProcessEventBus(EventBus):
    """Single-worker bus. Correct and dependency-free; does not cross processes."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        async with self._lock:
            self._history[topic].append(event)
            if len(self._history[topic]) > QUEUE_MAXSIZE:
                del self._history[topic][0]
            subscribers = list(self._subscribers.get(topic, ()))

        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("Dropping event for slow subscriber on %s", topic)

    async def subscribe(
        self, topic: str
    ) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers[topic].add(queue)
            backlog = list(self._history.get(topic, ()))
        return queue, backlog

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers[topic].discard(queue)
            if not self._subscribers[topic]:
                del self._subscribers[topic]

    async def clear(self, topic: str) -> None:
        async with self._lock:
            self._history.pop(topic, None)


class RedisEventBus(EventBus):
    """Multi-worker bus: publishes to a channel, replays from a capped list.

    The list is what makes late subscribers work. Redis pub/sub alone delivers
    only to whoever is already listening, so a client connecting a second after
    the run started would miss the beginning.
    """

    CHANNEL_PREFIX = "hct:events:"
    HISTORY_PREFIX = "hct:history:"

    def __init__(self, url: str) -> None:
        # Imported lazily so the redis package stays an optional dependency.
        from redis.asyncio import Redis

        self._redis = Redis.from_url(url, decode_responses=True)
        self._pumps: dict[asyncio.Queue[dict[str, Any]], asyncio.Task[None]] = {}

    def _channel(self, topic: str) -> str:
        return f"{self.CHANNEL_PREFIX}{topic}"

    def _history_key(self, topic: str) -> str:
        return f"{self.HISTORY_PREFIX}{topic}"

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, default=str)
        key = self._history_key(topic)
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.rpush(key, payload)
            pipe.ltrim(key, -QUEUE_MAXSIZE, -1)
            pipe.expire(key, HISTORY_TTL_SECONDS)
            pipe.publish(self._channel(topic), payload)
            await pipe.execute()

    async def subscribe(
        self, topic: str
    ) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel(topic))

        # Read history *after* subscribing, so nothing published in between is
        # lost. A duplicate is harmless; a gap is not.
        raw_history = await self._redis.lrange(self._history_key(topic), 0, -1)
        backlog = [json.loads(item) for item in raw_history]
        seen = len(backlog)

        async def pump() -> None:
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        queue.put_nowait(json.loads(message["data"]))
                    except asyncio.QueueFull:
                        logger.debug("Dropping event for slow subscriber on %s", topic)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a dead pump must not kill the request
                logger.exception("Redis event pump failed for %s", topic)
            finally:
                await pubsub.unsubscribe(self._channel(topic))
                await pubsub.aclose()

        self._pumps[queue] = asyncio.create_task(pump())
        logger.debug("Subscribed to %s with %d backlog events", topic, seen)
        return queue, backlog

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        task = self._pumps.pop(queue, None)
        if task is not None:
            task.cancel()
            # Teardown: the pump is being discarded, so nothing it raises on
            # the way out is actionable.
            with contextlib.suppress(Exception):
                await task

    async def clear(self, topic: str) -> None:
        await self._redis.delete(self._history_key(topic))

    async def aclose(self) -> None:
        for task in self._pumps.values():
            task.cancel()
        self._pumps.clear()
        await self._redis.aclose()


def build_event_bus() -> EventBus:
    """Redis when configured and importable, otherwise the in-process bus."""
    if settings.redis_url:
        try:
            bus = RedisEventBus(settings.redis_url)
        except ImportError:
            logger.warning(
                "REDIS_URL is set but the redis package is not installed; "
                "falling back to the in-process event bus. Run: pip install redis"
            )
        else:
            logger.info("Event bus: Redis (multi-worker safe)")
            return bus

    logger.info("Event bus: in-process (single worker only)")
    return InProcessEventBus()


event_bus: EventBus = build_event_bus()
