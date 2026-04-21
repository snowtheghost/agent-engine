from agent_engine.core.vault.chunk import VaultChunk
from agent_engine.infrastructure.vault.in_memory_vault_index import InMemoryVaultIndex


def _chunk(chunk_id: str, file_path: str, content: str, heading: str = "h") -> VaultChunk:
    return VaultChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        heading=heading,
        content=content,
    )


def test_upsert_and_search():
    index = InMemoryVaultIndex()
    index.upsert([
        _chunk("c1", "auth.md", "authentication flow uses oauth pkce"),
        _chunk("c2", "db.md", "database migration tooling based on alembic"),
    ])
    hits = index.search("oauth authentication", limit=3)
    assert hits
    assert hits[0][0].chunk_id == "c1"


def test_delete_by_file():
    index = InMemoryVaultIndex()
    index.upsert([
        _chunk("c1", "notes.md", "first chunk in notes"),
        _chunk("c2", "notes.md", "second chunk in notes"),
        _chunk("c3", "other.md", "chunk in other"),
    ])
    removed = index.delete_by_file("notes.md")
    assert removed == 2
    assert index.file_paths() == {"other.md"}


def test_search_filter_by_file():
    index = InMemoryVaultIndex()
    index.upsert([
        _chunk("c1", "a.md", "shared topic one"),
        _chunk("c2", "b.md", "shared topic two"),
    ])
    hits = index.search("shared topic", limit=5, file_filter="a.md")
    assert len(hits) == 1
    assert hits[0][0].file_path == "a.md"


def test_count_and_empty_search():
    index = InMemoryVaultIndex()
    assert index.count() == 0
    assert index.search("anything", limit=5) == []
