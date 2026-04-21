from agent_engine.infrastructure.vault.numpy_vector_store import NumpyVectorStore
from agent_engine.infrastructure.vault.persistent_vector_index import PersistentVectorIndex

import numpy as np
import pytest


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
    return PersistentVectorIndex(store=store)


def test_upsert_and_ids(index):
    index.upsert("e1", "hello world")
    index.upsert("e2", "foo bar")
    assert index.ids() == {"e1", "e2"}


def test_remove_drops_entry(index):
    index.upsert("e1", "hello")
    index.remove("e1")
    assert index.ids() == set()


def test_search_returns_results(index):
    index.upsert("e1", "authentication oauth")
    index.upsert("e2", "database migration")
    hits = index.search("oauth", limit=5)
    assert len(hits) == 2
    assert hits[0][0] in ("e1", "e2")


def test_search_empty_returns_empty(index):
    assert index.search("anything", limit=5) == []


def test_close_is_noop(index):
    index.upsert("e1", "hello")
    index.close()
