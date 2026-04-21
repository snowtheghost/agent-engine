from pathlib import Path

from agent_engine.core.vault.chunk import VaultChunk, VaultSearchHit


def test_chunk_is_frozen():
    chunk = VaultChunk(
        chunk_id="c1",
        file_path="notes.md",
        heading="Intro",
        content="Hello world.",
        tags=("a", "b"),
    )
    assert chunk.tags == ("a", "b")


def test_search_hit_carries_score_and_path():
    chunk = VaultChunk(chunk_id="c1", file_path="a.md", heading="h", content="x")
    hit = VaultSearchHit(chunk=chunk, score=0.5, path=Path("/tmp/a.md"))
    assert hit.score == 0.5
    assert hit.path == Path("/tmp/a.md")
