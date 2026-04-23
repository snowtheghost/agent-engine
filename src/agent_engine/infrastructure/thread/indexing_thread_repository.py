import structlog

from agent_engine.application.indexing.scheduler import IndexingScheduler
from agent_engine.application.thread.index.thread_index import ThreadIndex
from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.core.thread.model.thread import Thread, ThreadEntry
from agent_engine.infrastructure.thread.chunker import chunk_entry

logger = structlog.get_logger(__name__)


class IndexingThreadRepository(ThreadRepository):
    def __init__(
        self,
        inner: ThreadRepository,
        index: ThreadIndex,
        scheduler: IndexingScheduler,
    ) -> None:
        self._inner = inner
        self._index = index
        self._scheduler = scheduler

    def append(self, resume_key: str, entry: ThreadEntry) -> int:
        entry_index = self._inner.append(resume_key, entry)
        chunk = chunk_entry(resume_key, entry_index, entry)
        if chunk is None:
            return entry_index
        index = self._index
        self._scheduler.schedule(
            lambda: index.upsert([chunk]),
            name=f"thread_append:{resume_key}:{entry_index}",
        )
        return entry_index

    def load(self, resume_key: str) -> Thread | None:
        return self._inner.load(resume_key)

    def delete(self, resume_key: str) -> bool:
        removed = self._inner.delete(resume_key)
        index = self._index
        self._scheduler.schedule(
            lambda: index.delete_by_resume_key(resume_key),
            name=f"thread_delete:{resume_key}",
        )
        return removed

    def list_keys(self) -> list[str]:
        return self._inner.list_keys()

    def update_cursor(self, resume_key: str, cursor: int) -> None:
        self._inner.update_cursor(resume_key, cursor)
