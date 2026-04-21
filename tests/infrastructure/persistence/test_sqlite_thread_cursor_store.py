import pytest

from agent_engine.infrastructure.persistence.database import open_database
from agent_engine.infrastructure.persistence.sqlite_thread_cursor_store import (
    SqliteThreadCursorStore,
)


@pytest.fixture()
def store(tmp_path):
    connection = open_database(tmp_path / "test.db")
    yield SqliteThreadCursorStore(connection)
    connection.close()


def test_get_missing_returns_zero(store):
    assert store.get("unknown") == 0


def test_put_and_get(store):
    store.put("k1", 5)
    assert store.get("k1") == 5


def test_put_upserts(store):
    store.put("k1", 1)
    store.put("k1", 9)
    assert store.get("k1") == 9


def test_clear(store):
    store.put("k1", 3)
    store.clear("k1")
    assert store.get("k1") == 0
