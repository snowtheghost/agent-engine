import asyncio

import pytest

from agent_engine.application.indexing.indexer import (
    AsyncIndexingWorker,
    InlineIndexingScheduler,
)


def test_inline_scheduler_runs_immediately():
    scheduler = InlineIndexingScheduler()
    seen: list[int] = []

    scheduler.schedule(lambda: seen.append(1), name="test")

    assert seen == [1]


def test_inline_scheduler_swallows_exceptions():
    scheduler = InlineIndexingScheduler()

    def boom() -> None:
        raise RuntimeError("boom")

    scheduler.schedule(boom, name="test")


@pytest.mark.asyncio
async def test_async_worker_runs_scheduled_jobs():
    worker = AsyncIndexingWorker()
    await worker.start()

    seen: list[int] = []
    worker.schedule(lambda: seen.append(1), name="first")
    worker.schedule(lambda: seen.append(2), name="second")

    await worker.drain()
    await worker.stop()

    assert seen == [1, 2]


@pytest.mark.asyncio
async def test_async_worker_continues_after_failing_job():
    worker = AsyncIndexingWorker()
    await worker.start()

    seen: list[int] = []

    def boom() -> None:
        raise RuntimeError("boom")

    worker.schedule(boom, name="bad")
    worker.schedule(lambda: seen.append(42), name="good")

    await worker.drain()
    await worker.stop()

    assert seen == [42]


@pytest.mark.asyncio
async def test_async_worker_stop_is_idempotent():
    worker = AsyncIndexingWorker()
    await worker.start()
    await worker.stop()
    await worker.stop()


@pytest.mark.asyncio
async def test_async_worker_schedule_after_stop_is_noop():
    worker = AsyncIndexingWorker()
    await worker.start()
    await worker.stop()

    seen: list[int] = []
    worker.schedule(lambda: seen.append(1), name="late")

    await asyncio.sleep(0)
    assert seen == []
