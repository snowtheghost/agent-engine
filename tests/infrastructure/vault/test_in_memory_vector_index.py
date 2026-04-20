from agent_engine.infrastructure.vault.in_memory_vector_index import InMemoryVectorIndex


def test_upsert_and_search():
    index = InMemoryVectorIndex()
    index.upsert("e1", "authentication flow uses oauth pkce")
    index.upsert("e2", "database migration tooling based on alembic")
    index.upsert("e3", "auth session tokens stored in cookies")

    hits = index.search("oauth authentication", limit=3)
    assert hits[0][0] == "e1"
    assert "e2" not in [h[0] for h in hits]


def test_remove_drops_entry():
    index = InMemoryVectorIndex()
    index.upsert("e1", "hello world")
    index.remove("e1")
    assert index.search("hello", limit=5) == []


def test_search_empty_index():
    index = InMemoryVectorIndex()
    assert index.search("anything", limit=5) == []


def test_limit_is_respected():
    index = InMemoryVectorIndex()
    for i in range(10):
        index.upsert(f"e{i}", "the same words every time")
    hits = index.search("same words", limit=3)
    assert len(hits) == 3


def test_ids_returns_current_entries():
    index = InMemoryVectorIndex()
    assert index.ids() == set()
    index.upsert("e1", "x")
    index.upsert("e2", "y")
    assert index.ids() == {"e1", "e2"}
    index.remove("e1")
    assert index.ids() == {"e2"}
