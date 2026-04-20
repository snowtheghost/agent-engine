from datetime import datetime, timezone

import pytest

from agent_engine.core.vault.model.entry import VaultEntry
from agent_engine.infrastructure.persistence.database import open_database
from agent_engine.infrastructure.vault.sqlite_vault_repository import SqliteVaultRepository


@pytest.fixture()
def repository(tmp_path):
    connection = open_database(tmp_path / "test.db")
    yield SqliteVaultRepository(connection)
    connection.close()


def _entry(**overrides) -> VaultEntry:
    defaults = dict(
        entry_id="e1",
        kind="decision",
        title="Use WAL",
        body="Chose WAL for concurrency.",
        tags=("sqlite",),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return VaultEntry(**defaults)


def test_save_and_get_roundtrip(repository):
    entry = _entry()
    repository.save(entry)
    fetched = repository.get("e1")
    assert fetched is not None
    assert fetched.title == entry.title
    assert fetched.tags == entry.tags


def test_get_missing(repository):
    assert repository.get("missing") is None


def test_list_orders_by_created_at_desc(repository):
    first = _entry(entry_id="a", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = _entry(entry_id="b", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    repository.save(first)
    repository.save(second)

    entries = repository.list(10)
    assert [e.entry_id for e in entries] == ["b", "a"]


def test_delete_returns_true_when_removed(repository):
    repository.save(_entry())
    assert repository.delete("e1") is True
    assert repository.delete("e1") is False


def test_count(repository):
    for i in range(3):
        repository.save(_entry(entry_id=f"e{i}"))
    assert repository.count() == 3


def test_upsert_updates(repository):
    repository.save(_entry(title="Original"))
    repository.save(_entry(title="Updated"))
    assert repository.count() == 1
    assert repository.get("e1").title == "Updated"
