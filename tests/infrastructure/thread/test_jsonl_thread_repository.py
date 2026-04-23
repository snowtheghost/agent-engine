from datetime import UTC, datetime

import pytest

from agent_engine.application.thread.repository.thread_cursor_store import ThreadCursorStore
from agent_engine.core.thread.model.thread import AttachmentMetadata, ThreadEntry
from agent_engine.infrastructure.thread.persistence.jsonl_thread_repository import (
    JsonlThreadRepository,
)


class InMemoryCursorStore(ThreadCursorStore):

    def __init__(self) -> None:
        self.storage: dict[str, int] = {}

    def get(self, resume_key: str) -> int:
        return self.storage.get(resume_key, 0)

    def put(self, resume_key: str, cursor: int) -> None:
        self.storage[resume_key] = cursor

    def clear(self, resume_key: str) -> None:
        self.storage.pop(resume_key, None)


@pytest.fixture()
def repository(tmp_path):
    return JsonlThreadRepository(data_dir=tmp_path, cursor_store=InMemoryCursorStore())


def _entry(content: str = "hi", author: str = "alice") -> ThreadEntry:
    return ThreadEntry(
        author=author,
        content=content,
        attachments=(),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


def test_load_returns_none_when_file_missing(repository):
    assert repository.load("never") is None


def test_append_returns_entry_index(repository):
    first_index = repository.append("k1", _entry("first"))
    second_index = repository.append("k1", _entry("second"))
    third_index = repository.append("k1", _entry("third"))

    assert first_index == 0
    assert second_index == 1
    assert third_index == 2


def test_append_index_survives_reopen(tmp_path):
    cursor_store = InMemoryCursorStore()
    first = JsonlThreadRepository(data_dir=tmp_path, cursor_store=cursor_store)
    first.append("k1", _entry("first"))
    first.append("k1", _entry("second"))

    second = JsonlThreadRepository(data_dir=tmp_path, cursor_store=cursor_store)
    third_index = second.append("k1", _entry("third"))

    assert third_index == 2


def test_append_after_delete_resets_index(repository):
    repository.append("k1", _entry("first"))
    repository.append("k1", _entry("second"))
    repository.delete("k1")
    fresh_index = repository.append("k1", _entry("fresh"))

    assert fresh_index == 0


def test_append_and_load_round_trip(repository):
    entry = _entry("hello")
    repository.append("k1", entry)

    thread = repository.load("k1")
    assert thread is not None
    assert thread.resume_key == "k1"
    assert len(thread.entries) == 1
    assert thread.entries[0].author == "alice"
    assert thread.entries[0].content == "hello"
    assert thread.entries[0].timestamp.tzinfo is not None


def test_append_persists_attachments(repository):
    attachment = AttachmentMetadata(
        path="/tmp/a.png",
        filename="a.png",
        content_type="image/png",
        size=512,
        description="photo",
    )
    entry = ThreadEntry(
        author="alice",
        content="see",
        attachments=(attachment,),
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
    )
    repository.append("k1", entry)
    thread = repository.load("k1")
    assert thread is not None
    assert thread.entries[0].attachments == (attachment,)


def test_load_skips_corrupt_lines(tmp_path):
    cursor_store = InMemoryCursorStore()
    repository = JsonlThreadRepository(data_dir=tmp_path, cursor_store=cursor_store)
    repository.append("k1", _entry("good"))

    path = tmp_path / "threads" / "k1.jsonl"
    with open(path, "a", encoding="utf-8") as file:
        file.write("this is not json\n")
    repository.append("k1", _entry("also good"))

    thread = repository.load("k1")
    assert thread is not None
    contents = [entry.content for entry in thread.entries]
    assert contents == ["good", "also good"]


def test_delete_removes_file_and_cursor(repository):
    repository.append("k1", _entry())
    repository.update_cursor("k1", 1)
    assert repository.delete("k1") is True
    assert repository.load("k1") is None
    assert repository.delete("k1") is False


def test_list_keys_sorted_by_mtime_descending(tmp_path):
    repository = JsonlThreadRepository(data_dir=tmp_path, cursor_store=InMemoryCursorStore())
    repository.append("alpha", _entry())
    repository.append("beta", _entry())
    repository.append("gamma", _entry())

    beta_path = tmp_path / "threads" / "beta.jsonl"
    alpha_path = tmp_path / "threads" / "alpha.jsonl"
    gamma_path = tmp_path / "threads" / "gamma.jsonl"

    import os
    os.utime(alpha_path, (100, 100))
    os.utime(beta_path, (200, 200))
    os.utime(gamma_path, (300, 300))

    assert repository.list_keys() == ["gamma", "beta", "alpha"]


def test_list_keys_empty_when_no_threads(tmp_path):
    repository = JsonlThreadRepository(data_dir=tmp_path, cursor_store=InMemoryCursorStore())
    assert repository.list_keys() == []


def test_update_cursor_persists_through_store(repository):
    repository.append("k1", _entry())
    repository.append("k1", _entry("second"))
    repository.update_cursor("k1", 1)

    thread = repository.load("k1")
    assert thread is not None
    assert thread.read_cursor == 1


def test_slugifies_unsafe_resume_keys(tmp_path):
    repository = JsonlThreadRepository(data_dir=tmp_path, cursor_store=InMemoryCursorStore())
    repository.append("path/with/slashes", _entry())
    files = list((tmp_path / "threads").iterdir())
    assert len(files) == 1
    assert "/" not in files[0].name
    assert files[0].suffix == ".jsonl"
