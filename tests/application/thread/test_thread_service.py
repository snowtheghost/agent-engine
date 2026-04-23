from datetime import UTC, datetime

from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.application.thread.service.thread_service import (
    AGENT_AUTHOR,
    ThreadService,
)
from agent_engine.core.thread.model.thread import AttachmentMetadata, Thread, ThreadEntry


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
        thread = self._threads.get(resume_key)
        if thread is None:
            thread = Thread(resume_key=resume_key)
            self._threads[resume_key] = thread
        thread.read_cursor = cursor


def _entry(author: str, content: str) -> ThreadEntry:
    return ThreadEntry(
        author=author,
        content=content,
        attachments=(),
        timestamp=datetime.now(UTC),
    )


def test_handle_message_appends_and_returns_single_entry_prompt() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)

    prompt = service.handle_message("k1", _entry("alice", "hello"))

    assert prompt is not None
    assert "[From: alice]" in prompt
    assert "hello" in prompt
    assert "[Queued messages" not in prompt
    thread = repository.load("k1")
    assert thread is not None
    assert len(thread.entries) == 1


def test_get_pending_prompts_returns_none_when_only_agent_entries() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    repository.append("k1", _entry(AGENT_AUTHOR, "hi there"))

    pending = service.get_pending_prompts("k1")
    assert pending is None


def test_get_pending_prompts_filters_agent_replies() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    repository.append("k1", _entry("alice", "first"))
    repository.append("k1", _entry(AGENT_AUTHOR, "answer"))
    repository.append("k1", _entry("alice", "second"))

    pending = service.get_pending_prompts("k1")
    assert pending is not None
    prompt, cursor = pending
    assert "first" in prompt
    assert "second" in prompt
    assert "answer" not in prompt
    assert "[Queued messages while you were working:]" in prompt
    assert cursor == 3


def test_get_pending_prompts_combined_header_only_when_multiple() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    repository.append("k1", _entry("alice", "one"))

    pending = service.get_pending_prompts("k1")
    assert pending is not None
    prompt, _ = pending
    assert "[Queued messages while you were working:]" not in prompt

    repository.append("k1", _entry("alice", "two"))
    pending_two = service.get_pending_prompts("k1")
    assert pending_two is not None
    prompt_two, _ = pending_two
    assert prompt_two.startswith("[Queued messages while you were working:]")


def test_get_pending_prompts_respects_read_cursor() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    repository.append("k1", _entry("alice", "before"))
    repository.update_cursor("k1", 1)
    repository.append("k1", _entry("alice", "after"))

    pending = service.get_pending_prompts("k1")
    assert pending is not None
    prompt, cursor = pending
    assert "before" not in prompt
    assert "after" in prompt
    assert cursor == 2


def test_acknowledge_advances_cursor() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    repository.append("k1", _entry("alice", "one"))
    repository.append("k1", _entry("alice", "two"))

    service.acknowledge("k1", 2)

    thread = repository.load("k1")
    assert thread is not None
    assert thread.read_cursor == 2


def test_log_reply_appends_agent_entry() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    service.log_reply("k1", "hello from agent")

    thread = repository.load("k1")
    assert thread is not None
    assert len(thread.entries) == 1
    assert thread.entries[0].author == AGENT_AUTHOR
    assert thread.entries[0].content == "hello from agent"


def test_get_thread_returns_none_when_absent() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    assert service.get_thread("missing") is None


def test_list_threads_paginates() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    repository.append("a", _entry("alice", "a"))
    repository.append("b", _entry("alice", "b"))
    repository.append("c", _entry("alice", "c"))

    all_keys = service.list_threads()
    assert set(all_keys) == {"a", "b", "c"}

    limited = service.list_threads(limit=2)
    assert len(limited) == 2

    offset = service.list_threads(limit=2, offset=2)
    assert len(offset) == 1


def test_prompt_includes_attachments() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    attachment = AttachmentMetadata(
        path="/tmp/a.png",
        filename="a.png",
        content_type="image/png",
        size=2048,
        description="a puppy",
    )
    entry = ThreadEntry(
        author="alice",
        content="see pic",
        attachments=(attachment,),
        timestamp=datetime.now(UTC),
    )
    repository.append("k1", entry)

    pending = service.get_pending_prompts("k1")
    assert pending is not None
    prompt, _ = pending
    assert "[Attachments:]" in prompt
    assert "a.png" in prompt
    assert "a puppy" in prompt


def test_cursor_does_not_advance_on_read() -> None:
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    repository.append("k1", _entry("alice", "one"))
    service.get_pending_prompts("k1")
    service.get_pending_prompts("k1")

    thread = repository.load("k1")
    assert thread is not None
    assert thread.read_cursor == 0
