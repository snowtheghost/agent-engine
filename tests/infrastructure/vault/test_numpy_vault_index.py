import numpy as np
import pytest

from agent_engine.core.vault.chunk import VaultChunk
from agent_engine.infrastructure.vault.numpy_vault_index import NumpyVaultIndex
from agent_engine.infrastructure.vault.numpy_vector_store import NumpyVectorStore


def _simple_embed(texts: list[str]) -> np.ndarray:
    n = len(texts)
    dim = 8
    embeddings = np.zeros((n, dim), dtype=np.float32)
    for i, text in enumerate(texts):
        for j, ch in enumerate(text[:dim]):
            embeddings[i, j % dim] = ord(ch)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return embeddings / norms


@pytest.fixture()
def index(tmp_path):
    store = NumpyVectorStore(
        store_dir=tmp_path / "store",
        name="test",
        embed_fn=_simple_embed,
        embedding_dim=8,
    )
    return NumpyVaultIndex(store=store)


def _chunk(chunk_id: str, file_path: str, content: str) -> VaultChunk:
    return VaultChunk(chunk_id=chunk_id, file_path=file_path, heading="h", content=content)


def test_upsert_and_search(index):
    index.upsert([
        _chunk("c1", "a.md", "authentication oauth"),
        _chunk("c2", "b.md", "database migration"),
    ])
    hits = index.search("oauth", limit=5)
    assert len(hits) == 2


def test_delete_by_file_drops_all_chunks_for_that_file(index):
    index.upsert([
        _chunk("c1", "a.md", "one"),
        _chunk("c2", "a.md", "two"),
        _chunk("c3", "b.md", "three"),
    ])
    removed = index.delete_by_file("a.md")
    assert removed == 2
    assert index.file_paths() == {"b.md"}


def test_search_filter_by_file(index):
    index.upsert([
        _chunk("c1", "a.md", "shared"),
        _chunk("c2", "b.md", "shared"),
    ])
    hits = index.search("shared", limit=5, file_filter="b.md")
    assert [h[0].file_path for h in hits] == ["b.md"]


def test_search_returns_empty_when_store_empty(index):
    assert index.search("anything", limit=5) == []


def test_close_noop(index):
    index.upsert([_chunk("c1", "a.md", "x")])
    index.close()
