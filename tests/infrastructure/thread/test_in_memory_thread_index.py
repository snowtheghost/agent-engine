from datetime import UTC, datetime

from agent_engine.core.thread.model.chunk import ThreadChunk
from agent_engine.infrastructure.thread.in_memory_thread_index import InMemoryThreadIndex


def _chunk(
    chunk_id: str = "c1",
    resume_key: str = "k",
    entry_index: int = 0,
    content: str = "hello world",
) -> ThreadChunk:
    return ThreadChunk(
        chunk_id=chunk_id,
        resume_key=resume_key,
        entry_index=entry_index,
        author="alice",
        timestamp=datetime(2026, 4, 22, tzinfo=UTC),
        content=content,
    )


def test_upsert_and_search_returns_match():
    index = InMemoryThreadIndex()
    index.upsert([_chunk(content="discuss monorepo migration progress today")])

    hits = index.search("monorepo migration", limit=5)
    assert hits
    chunk, score = hits[0]
    assert chunk.resume_key == "k"
    assert score > 0.0


def test_search_no_match_returns_empty():
    index = InMemoryThreadIndex()
    index.upsert([_chunk(content="totally unrelated content about cooking")])

    hits = index.search("monorepo migration", limit=5)
    assert hits == []


def test_search_resume_key_filter():
    index = InMemoryThreadIndex()
    index.upsert(
        [
            _chunk(chunk_id="a", resume_key="k1", content="monorepo migration topic"),
            _chunk(chunk_id="b", resume_key="k2", content="monorepo migration topic"),
        ]
    )

    hits = index.search("monorepo migration", limit=10, resume_key_filter="k1")
    assert len(hits) == 1
    assert hits[0][0].resume_key == "k1"


def test_delete_by_resume_key():
    index = InMemoryThreadIndex()
    index.upsert(
        [
            _chunk(chunk_id="a", resume_key="k1", content="long content one here today"),
            _chunk(chunk_id="b", resume_key="k2", content="long content two here today"),
        ]
    )

    removed = index.delete_by_resume_key("k1")
    assert removed == 1
    assert index.count() == 1
    assert index.resume_keys() == {"k2"}


def test_resume_keys_returns_unique_set():
    index = InMemoryThreadIndex()
    index.upsert(
        [
            _chunk(chunk_id="a", resume_key="k1", entry_index=0, content="first entry content"),
            _chunk(chunk_id="b", resume_key="k1", entry_index=1, content="second entry content"),
            _chunk(chunk_id="c", resume_key="k2", entry_index=0, content="other thread content"),
        ]
    )
    assert index.resume_keys() == {"k1", "k2"}


def test_upsert_replaces_existing_chunk():
    index = InMemoryThreadIndex()
    index.upsert([_chunk(chunk_id="a", content="initial content here now please")])
    assert index.count() == 1

    index.upsert([_chunk(chunk_id="a", content="replacement content here now please")])
    assert index.count() == 1

    hits = index.search("replacement", limit=5)
    assert hits
    assert "replacement" in hits[0][0].content
