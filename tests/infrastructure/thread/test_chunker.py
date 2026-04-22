from datetime import UTC, datetime

from agent_engine.core.thread.model.thread import AttachmentMetadata, ThreadEntry
from agent_engine.infrastructure.thread.chunker import chunk_entries, chunk_entry


def _entry(content: str, attachments: tuple[AttachmentMetadata, ...] = ()) -> ThreadEntry:
    return ThreadEntry(
        author="alice",
        content=content,
        attachments=attachments,
        timestamp=datetime(2026, 4, 22, tzinfo=UTC),
    )


def test_chunk_entry_returns_none_for_short_content():
    entry = _entry(content="hi")
    assert chunk_entry("k", 0, entry) is None


def test_chunk_entry_includes_content():
    entry = _entry(content="This is a meaningful message about icebox workflows.")
    chunk = chunk_entry("conv-1", 3, entry)
    assert chunk is not None
    assert chunk.resume_key == "conv-1"
    assert chunk.entry_index == 3
    assert chunk.author == "alice"
    assert "icebox workflows" in chunk.content


def test_chunk_entry_deterministic_id():
    entry = _entry(content="deterministic content example for testing")
    first = chunk_entry("k", 0, entry)
    second = chunk_entry("k", 0, entry)
    assert first is not None
    assert second is not None
    assert first.chunk_id == second.chunk_id


def test_chunk_entry_id_varies_with_index():
    entry = _entry(content="same content same author long enough to chunk now")
    a = chunk_entry("k", 0, entry)
    b = chunk_entry("k", 1, entry)
    assert a is not None
    assert b is not None
    assert a.chunk_id != b.chunk_id


def test_chunk_entry_includes_attachment_description():
    attachment = AttachmentMetadata(
        path="/tmp/image.png",
        filename="image.png",
        content_type="image/png",
        size=1024,
        description="a graph showing goalie workflow triage",
    )
    entry = _entry(content="check this out please", attachments=(attachment,))
    chunk = chunk_entry("k", 0, entry)
    assert chunk is not None
    assert "graph showing goalie workflow triage" in chunk.content
    assert "image.png" in chunk.content


def test_chunk_entries_skips_short_entries():
    entries = [
        _entry(content="hi"),
        _entry(content="the quick brown fox jumps over the lazy dog today"),
    ]
    chunks = chunk_entries("k", entries)
    assert len(chunks) == 1
    assert chunks[0].entry_index == 1
