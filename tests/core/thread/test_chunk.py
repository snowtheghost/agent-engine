from datetime import UTC, datetime

from agent_engine.core.thread.model.chunk import ThreadChunk, ThreadSearchHit


def test_chunk_is_frozen():
    chunk = ThreadChunk(
        chunk_id="c1",
        resume_key="k",
        entry_index=0,
        author="alice",
        timestamp=datetime.now(UTC),
        content="Hello world.",
    )
    assert chunk.author == "alice"


def test_search_hit_carries_score():
    chunk = ThreadChunk(
        chunk_id="c1",
        resume_key="k",
        entry_index=0,
        author="alice",
        timestamp=datetime.now(UTC),
        content="x",
    )
    hit = ThreadSearchHit(chunk=chunk, score=0.5)
    assert hit.score == 0.5
    assert hit.chunk.resume_key == "k"
