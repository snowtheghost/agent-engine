from datetime import UTC, datetime

from agent_engine.core.thread.model.thread import AttachmentMetadata, Thread, ThreadEntry


def _entry(author: str = "alice", content: str = "hi") -> ThreadEntry:
    return ThreadEntry(
        author=author,
        content=content,
        attachments=(),
        timestamp=datetime.now(UTC),
    )


def test_attachment_metadata_is_frozen() -> None:
    attachment = AttachmentMetadata(
        path="/tmp/a",
        filename="a",
        content_type="text/plain",
        size=1,
        description="",
    )
    assert attachment.filename == "a"
    try:
        attachment.filename = "b"  # type: ignore[misc]
    except Exception as error:
        assert isinstance(error, (AttributeError, Exception))
    else:
        raise AssertionError("expected frozen dataclass to reject mutation")


def test_thread_defaults_cursor_to_zero_and_empty_entries() -> None:
    thread = Thread(resume_key="k")
    assert thread.entries == []
    assert thread.read_cursor == 0


def test_append_adds_entry_in_order() -> None:
    thread = Thread(resume_key="k")
    first = _entry(content="a")
    second = _entry(content="b")
    thread.append(first)
    thread.append(second)
    assert thread.entries == [first, second]


def test_unread_from_returns_slice_after_cursor() -> None:
    thread = Thread(resume_key="k")
    a = _entry(content="a")
    b = _entry(content="b")
    c = _entry(content="c")
    thread.append(a)
    thread.append(b)
    thread.append(c)
    assert thread.unread_from(0) == [a, b, c]
    assert thread.unread_from(1) == [b, c]
    assert thread.unread_from(3) == []
