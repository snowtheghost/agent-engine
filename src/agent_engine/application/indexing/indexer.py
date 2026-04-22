import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


IndexingJob = Callable[[], None]


@runtime_checkable
class IndexingScheduler(Protocol):
    def schedule(self, job: IndexingJob, *, name: str) -> None: ...


class InlineIndexingScheduler:
    def schedule(self, job: IndexingJob, *, name: str) -> None:
        try:
            job()
        except Exception:
            logger.exception("inline_indexing_job_failed", name=name)


class AsyncIndexingWorker:
    def __init__(self, queue_maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[tuple[IndexingJob, str]] = asyncio.Queue(queue_maxsize)
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def schedule(self, job: IndexingJob, *, name: str) -> None:
        if self._stopping:
            logger.warning("indexing_job_dropped_after_stop", name=name)
            return
        try:
            self._queue.put_nowait((job, name))
        except asyncio.QueueFull:
            logger.warning("indexing_queue_full", name=name)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="indexing-worker")
        logger.info("indexing_worker_started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping = True
        await self._queue.join()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
        logger.info("indexing_worker_stopped")

    async def drain(self) -> None:
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            job, name = await self._queue.get()
            try:
                await asyncio.to_thread(_run_job, job, name)
            finally:
                self._queue.task_done()


def _run_job(job: IndexingJob, name: str) -> None:
    try:
        result = job()
        if isinstance(result, Awaitable):
            logger.warning("indexing_job_returned_awaitable", name=name)
    except Exception:
        logger.exception("indexing_job_failed", name=name)
