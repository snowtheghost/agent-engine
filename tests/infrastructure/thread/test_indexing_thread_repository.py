from datetime import UTC, datetime

from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.core.thread.model.thread import Thread, ThreadEntry
from agent_engine.infrastructure.indexing.inline_scheduler import InlineIndexingScheduler
from agent_engine.infrastructure.thread.in_memory_thread_index import InMemoryThreadIndex
from agent_engine.infrastructure.thread.indexing_thread_repository import (
    IndexingThreadRepository,
)


class InMemoryThreadRepository(ThreadRepository):
    def __init__(self) -> None:
        self._threads: dict[str, Thread] = {}

    def append(self, resume_key: str, entry: ThreadEntry) -> int:
        thread = self._threads.setdefault(resume_key, Thread(resume_key=resume_key))
        thread.entries.append(entry)
        return len(thread.entries) - 1

    def load(self, resume_key: str) -> Thread | None:
        return self._threads.get(resume_key)

    def delete(self, resume_key: str) -> bool:
        return self._threads.pop(resume_key, None) is not None

    def list_keys(self) -> list[str]:
        return list(self._threads.keys())

    def update_cursor(self, resume_key: str, cursor: int) -> None:
        thread = self._threads.setdefault(resume_key, Thread(resume_key=resume_key))
        thread.read_cursor = cursor


def _entry(content: str) -> ThreadEntry:
    return ThreadEntry(
        author="alice",
        content=content,
        attachments=(),
        timestamp=datetime(2026, 4, 22, tzinfo=UTC),
    )


def test_append_indexes_entry():
    inner = InMemoryThreadRepository()
    index = InMemoryThreadIndex()
    scheduler = InlineIndexingScheduler()
    repository = IndexingThreadRepository(inner=inner, index=index, scheduler=scheduler)

    repository.append("k1", _entry("discuss icebox monorepo migration plan"))

    hits = index.search("icebox monorepo", limit=5)
    assert hits
    assert hits[0][0].resume_key == "k1"
    assert hits[0][0].entry_index == 0


def test_append_short_content_not_indexed():
    inner = InMemoryThreadRepository()
    index = InMemoryThreadIndex()
    repository = IndexingThreadRepository(
        inner=inner, index=index, scheduler=InlineIndexingScheduler()
    )

    repository.append("k1", _entry("hi"))

    assert index.count() == 0
    thread = inner.load("k1")
    assert thread is not None
    assert len(thread.entries) == 1


def test_delete_removes_chunks():
    inner = InMemoryThreadRepository()
    index = InMemoryThreadIndex()
    repository = IndexingThreadRepository(
        inner=inner, index=index, scheduler=InlineIndexingScheduler()
    )

    repository.append("k1", _entry("long content about icebox workflows today"))
    assert index.count() == 1

    repository.delete("k1")

    assert index.count() == 0
