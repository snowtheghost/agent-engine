import pytest

from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.infrastructure.persistence.database import open_database
from agent_engine.infrastructure.persistence.sqlite_resume_handle_store import (
    SqliteResumeHandleStore,
)


@pytest.fixture()
def store(tmp_path):
    connection = open_database(tmp_path / "test.db")
    yield SqliteResumeHandleStore(connection)
    connection.close()


def test_put_and_get(store):
    store.put("thread-1", ResumeHandle(provider="claude", session_id="abc"))
    handle = store.get("thread-1")
    assert handle is not None
    assert handle.provider == "claude"
    assert handle.session_id == "abc"


def test_get_missing_returns_none(store):
    assert store.get("nope") is None


def test_put_upserts(store):
    store.put("thread-1", ResumeHandle(provider="claude", session_id="v1"))
    store.put("thread-1", ResumeHandle(provider="claude", session_id="v2"))
    handle = store.get("thread-1")
    assert handle is not None
    assert handle.session_id == "v2"


def test_clear(store):
    store.put("thread-1", ResumeHandle(provider="claude", session_id="abc"))
    store.clear("thread-1")
    assert store.get("thread-1") is None
