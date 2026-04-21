from pathlib import Path

import numpy as np
import pytest

from agent_engine.infrastructure.vault.numpy_vector_store import (
    NumpyVectorStore,
    _matches_filter,
)


def _identity_embed(texts: list[str]) -> np.ndarray:
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
def store(tmp_path):
    return NumpyVectorStore(
        store_dir=tmp_path / "store",
        name="test",
        embed_fn=_identity_embed,
        embedding_dim=8,
    )


class TestMatchesFilter:

    def test_empty_where_matches_everything(self):
        assert _matches_filter({"a": "1"}, {}) is True

    def test_exact_match(self):
        assert _matches_filter({"a": "1"}, {"a": "1"}) is True
        assert _matches_filter({"a": "1"}, {"a": "2"}) is False

    def test_missing_key_is_empty_string(self):
        assert _matches_filter({}, {"a": ""}) is True
        assert _matches_filter({}, {"a": "x"}) is False

    def test_contains(self):
        assert _matches_filter({"a": "hello world"}, {"a": {"$contains": "world"}}) is True
        assert _matches_filter({"a": "hello"}, {"a": {"$contains": "world"}}) is False

    def test_ne(self):
        assert _matches_filter({"a": "1"}, {"a": {"$ne": "2"}}) is True
        assert _matches_filter({"a": "1"}, {"a": {"$ne": "1"}}) is False

    def test_and(self):
        meta = {"a": "1", "b": "2"}
        assert _matches_filter(meta, {"$and": [{"a": "1"}, {"b": "2"}]}) is True
        assert _matches_filter(meta, {"$and": [{"a": "1"}, {"b": "3"}]}) is False

    def test_or(self):
        meta = {"a": "1", "b": "2"}
        assert _matches_filter(meta, {"$or": [{"a": "1"}, {"b": "3"}]}) is True
        assert _matches_filter(meta, {"$or": [{"a": "3"}, {"b": "3"}]}) is False

    def test_multiple_keys_all_must_match(self):
        assert _matches_filter({"a": "1", "b": "2"}, {"a": "1", "b": "2"}) is True
        assert _matches_filter({"a": "1", "b": "2"}, {"a": "1", "b": "3"}) is False


class TestNumpyVectorStore:

    def test_starts_empty(self, store):
        assert store.count() == 0

    def test_upsert_adds_entries(self, store):
        store.upsert(
            ids=["e1", "e2"],
            documents=["hello world", "foo bar"],
            metadatas=[{"tag": "a"}, {"tag": "b"}],
        )
        assert store.count() == 2

    def test_upsert_updates_existing(self, store):
        store.upsert(ids=["e1"], documents=["old"], metadatas=[{"v": 1}])
        store.upsert(ids=["e1"], documents=["new"], metadatas=[{"v": 2}])
        assert store.count() == 1
        result = store.get(ids=["e1"])
        assert result["documents"][0] == "new"
        assert result["metadatas"][0]["v"] == 2

    def test_upsert_empty_is_noop(self, store):
        store.upsert(ids=[], documents=[], metadatas=[])
        assert store.count() == 0

    def test_delete_removes_entries(self, store):
        store.upsert(ids=["e1", "e2"], documents=["a", "b"], metadatas=[{}, {}])
        store.delete(ids=["e1"])
        assert store.count() == 1
        assert store.get()["ids"] == ["e2"]

    def test_delete_empty_is_noop(self, store):
        store.upsert(ids=["e1"], documents=["a"], metadatas=[{}])
        store.delete(ids=[])
        assert store.count() == 1

    def test_delete_nonexistent_is_noop(self, store):
        store.upsert(ids=["e1"], documents=["a"], metadatas=[{}])
        store.delete(ids=["missing"])
        assert store.count() == 1

    def test_get_with_ids_filter(self, store):
        store.upsert(ids=["e1", "e2"], documents=["a", "b"], metadatas=[{}, {}])
        result = store.get(ids=["e2"])
        assert result["ids"] == ["e2"]

    def test_get_with_where_filter(self, store):
        store.upsert(
            ids=["e1", "e2"],
            documents=["a", "b"],
            metadatas=[{"tag": "x"}, {"tag": "y"}],
        )
        result = store.get(where={"tag": "y"})
        assert result["ids"] == ["e2"]

    def test_get_returns_all_without_filters(self, store):
        store.upsert(ids=["e1", "e2"], documents=["a", "b"], metadatas=[{}, {}])
        result = store.get()
        assert set(result["ids"]) == {"e1", "e2"}

    def test_query_returns_sorted_by_similarity(self, store):
        store.upsert(
            ids=["e1", "e2", "e3"],
            documents=["alpha", "alpha2", "zzzzz"],
            metadatas=[{}, {}, {}],
        )
        results = store.query(query_texts=["alpha"], n_results=3)
        assert len(results["ids"][0]) == 3
        assert results["ids"][0][0] in ("e1", "e2")

    def test_query_with_where_filter(self, store):
        store.upsert(
            ids=["e1", "e2"],
            documents=["alpha", "alpha2"],
            metadatas=[{"tag": "a"}, {"tag": "b"}],
        )
        results = store.query(query_texts=["alpha"], n_results=10, where={"tag": "b"})
        assert results["ids"][0] == ["e2"]

    def test_query_empty_store(self, store):
        results = store.query(query_texts=["anything"], n_results=5)
        assert results["ids"] == [[]]

    def test_query_empty_texts(self, store):
        results = store.query(query_texts=[], n_results=5)
        assert results["ids"] == [[]]

    def test_query_respects_n_results(self, store):
        for i in range(10):
            store.upsert(
                ids=[f"e{i}"],
                documents=[f"doc {i}"],
                metadatas=[{}],
            )
        results = store.query(query_texts=["doc"], n_results=3)
        assert len(results["ids"][0]) == 3

    def test_reset_clears_everything(self, store):
        store.upsert(ids=["e1"], documents=["a"], metadatas=[{}])
        store.reset()
        assert store.count() == 0
        assert not (store._emb_path.exists())
        assert not (store._index_path.exists())


class TestPersistence:

    def test_data_survives_reopen(self, tmp_path):
        store_dir = tmp_path / "store"
        store1 = NumpyVectorStore(
            store_dir=store_dir,
            name="test",
            embed_fn=_identity_embed,
            embedding_dim=8,
        )
        store1.upsert(
            ids=["e1"],
            documents=["hello"],
            metadatas=[{"tag": "a"}],
        )
        assert store1.count() == 1

        store2 = NumpyVectorStore(
            store_dir=store_dir,
            name="test",
            embed_fn=_identity_embed,
            embedding_dim=8,
        )
        assert store2.count() == 1
        result = store2.get(ids=["e1"])
        assert result["documents"][0] == "hello"
        assert result["metadatas"][0]["tag"] == "a"

    def test_dimension_mismatch_clears_store(self, tmp_path):
        store_dir = tmp_path / "store"
        store1 = NumpyVectorStore(
            store_dir=store_dir,
            name="test",
            embed_fn=_identity_embed,
            embedding_dim=8,
        )
        store1.upsert(ids=["e1"], documents=["hello"], metadatas=[{}])

        store2 = NumpyVectorStore(
            store_dir=store_dir,
            name="test",
            embed_fn=_identity_embed,
            embedding_dim=16,
        )
        assert store2.count() == 0

    def test_inconsistent_count_clears_store(self, tmp_path):
        store_dir = tmp_path / "store"
        store = NumpyVectorStore(
            store_dir=store_dir,
            name="test",
            embed_fn=_identity_embed,
            embedding_dim=8,
        )
        store.upsert(ids=["e1"], documents=["hello"], metadatas=[{}])

        import json
        index_path = store_dir / "test_index.json"
        data = json.loads(index_path.read_text())
        data["ids"].append("ghost")
        index_path.write_text(json.dumps(data))

        store2 = NumpyVectorStore(
            store_dir=store_dir,
            name="test",
            embed_fn=_identity_embed,
            embedding_dim=8,
        )
        assert store2.count() == 0


class TestQueryEmbedFn:

    def test_uses_separate_query_embed_fn(self, tmp_path):
        call_log: list[str] = []

        def doc_embed(texts: list[str]) -> np.ndarray:
            call_log.extend(["doc"] * len(texts))
            return _identity_embed(texts)

        def query_embed(texts: list[str]) -> np.ndarray:
            call_log.extend(["query"] * len(texts))
            return _identity_embed(texts)

        store = NumpyVectorStore(
            store_dir=tmp_path / "store",
            name="test",
            embed_fn=doc_embed,
            embedding_dim=8,
            query_embed_fn=query_embed,
        )
        store.upsert(ids=["e1"], documents=["hello"], metadatas=[{}])
        store.query(query_texts=["search"], n_results=5)

        assert "doc" in call_log
        assert "query" in call_log
