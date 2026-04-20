import pytest

from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.infrastructure.persistence.database import open_database
from agent_engine.infrastructure.vault.in_memory_vector_index import InMemoryVectorIndex
from agent_engine.infrastructure.vault.sqlite_vault_repository import SqliteVaultRepository


@pytest.fixture()
def vault(tmp_path):
    connection = open_database(tmp_path / "test.db")
    repository = SqliteVaultRepository(connection)
    index = InMemoryVectorIndex()
    yield VaultService(repository=repository, index=index)
    connection.close()


def test_write_then_search(vault):
    vault.write(kind="decision", title="Use WAL", body="Better concurrency story.")
    vault.write(kind="pattern", title="Retry with backoff", body="Exponential backoff for transient errors.")
    vault.write(kind="gotcha", title="GIL", body="Threads share memory but not CPU.")

    hits = vault.search("concurrency", limit=5)
    assert hits
    assert hits[0].entry.title == "Use WAL"


def test_recall_returns_full_entry(vault):
    entry = vault.write(kind="note", title="hello", body="world")
    recalled = vault.recall(entry.entry_id)
    assert recalled is not None
    assert recalled.body == "world"


def test_list_and_count(vault):
    for i in range(3):
        vault.write(kind="note", title=f"n{i}", body=f"body{i}")
    assert vault.count() == 3
    assert len(vault.list(10)) == 3


def test_delete_removes_from_both_repo_and_index(vault):
    entry = vault.write(kind="note", title="x", body="oauth2 secret")
    assert vault.delete(entry.entry_id) is True
    assert vault.recall(entry.entry_id) is None
    assert vault.search("oauth2", limit=5) == []


def test_search_returns_empty_when_no_match(vault):
    vault.write(kind="note", title="apples", body="red fruit")
    assert vault.search("spacecraft", limit=5) == []


def test_tags_are_preserved(vault):
    entry = vault.write(kind="note", title="t", body="b", tags=("a", "b"))
    recalled = vault.recall(entry.entry_id)
    assert recalled.tags == ("a", "b")
