from datetime import UTC, datetime

from agent_engine.core.thread.model.thread import ThreadEntry
from agent_engine.infrastructure.thread.in_memory_thread_index import InMemoryThreadIndex
from agent_engine.infrastructure.thread.jsonl_thread_scanner import JsonlThreadScanner
from agent_engine.infrastructure.thread.persistence.jsonl_thread_repository import (
    JsonlThreadRepository,
)


class InMemoryCursorStore:
    def __init__(self) -> None:
        self._cursors: dict[str, int] = {}

    def get(self, resume_key: str) -> int:
        return self._cursors.get(resume_key, 0)

    def put(self, resume_key: str, cursor: int) -> None:
        self._cursors[resume_key] = cursor

    def clear(self, resume_key: str) -> None:
        self._cursors.pop(resume_key, None)


def _entry(content: str) -> ThreadEntry:
    return ThreadEntry(
        author="alice",
        content=content,
        attachments=(),
        timestamp=datetime(2026, 4, 22, tzinfo=UTC),
    )


def _build(tmp_path):
    cursor_store = InMemoryCursorStore()
    repository = JsonlThreadRepository(data_dir=tmp_path, cursor_store=cursor_store)
    index = InMemoryThreadIndex()
    scanner = JsonlThreadScanner(
        threads_dir=tmp_path / "threads",
        repository=repository,
        index=index,
    )
    return repository, index, scanner


def test_scan_indexes_existing_threads(tmp_path):
    repository, index, scanner = _build(tmp_path)
    repository.append("k1", _entry("monorepo migration discussion content"))
    repository.append("k2", _entry("icebox workflow troubleshooting session"))

    report = scanner.scan()

    assert report.indexed_threads == 2
    assert report.total_chunks == 2
    hits = index.search("monorepo migration", limit=5)
    assert hits
    assert hits[0][0].resume_key == "k1"


def test_scan_skips_unchanged_threads(tmp_path):
    repository, _, scanner = _build(tmp_path)
    repository.append("k1", _entry("some content long enough to be chunked here"))

    first = scanner.scan()
    assert first.indexed_threads == 1

    second = scanner.scan()
    assert second.indexed_threads == 0
    assert second.skipped_unchanged == 1


def test_scan_detects_deleted_threads(tmp_path):
    repository, index, scanner = _build(tmp_path)
    repository.append("k1", _entry("first thread content here long enough"))
    repository.append("k2", _entry("second thread content here long enough"))

    scanner.scan()
    assert index.count() == 2

    (tmp_path / "threads" / "k1.jsonl").unlink()
    report = scanner.scan()

    assert report.removed_threads == 1
    assert index.resume_keys() == {"k2"}


def test_scan_reindexes_when_entries_appended(tmp_path):
    repository, index, scanner = _build(tmp_path)
    repository.append("k1", _entry("first entry content here long enough to chunk"))
    scanner.scan()
    assert index.count() == 1

    repository.append("k1", _entry("second entry content here long enough to chunk"))
    scanner.scan()

    assert index.count() == 2
