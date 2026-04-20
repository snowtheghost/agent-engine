from datetime import datetime, timezone

import pytest

from agent_engine.core.vault.model.entry import VaultEntry
from agent_engine.infrastructure.vault.file_vault_repository import FileVaultRepository


@pytest.fixture()
def repository(tmp_path):
    return FileVaultRepository(tmp_path / "vault")


def _entry(**overrides) -> VaultEntry:
    defaults = dict(
        entry_id="e1",
        kind="decision",
        title="Use WAL",
        body="Chose WAL for concurrency.",
        tags=("sqlite",),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return VaultEntry(**defaults)


def test_save_writes_markdown_with_frontmatter(repository):
    entry = _entry()
    path = repository.save(entry)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "id: e1" in text
    assert "kind: decision" in text
    assert "title: Use WAL" in text
    assert "Chose WAL for concurrency." in text


def test_get_returns_entry_from_disk(repository):
    repository.save(_entry())
    fetched = repository.get("e1")
    assert fetched is not None
    assert fetched.title == "Use WAL"
    assert fetched.tags == ("sqlite",)


def test_get_missing_returns_none(repository):
    assert repository.get("missing") is None


def test_path_for_returns_none_when_missing(repository):
    assert repository.path_for("missing") is None


def test_path_for_returns_existing(repository, tmp_path):
    repository.save(_entry())
    path = repository.path_for("e1")
    assert path is not None
    assert path == tmp_path / "vault" / "e1.md"


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
    assert repository.get("e1") is None


def test_count(repository):
    for i in range(3):
        repository.save(_entry(entry_id=f"e{i}"))
    assert repository.count() == 3


def test_save_overwrites_existing(repository):
    repository.save(_entry(title="Original"))
    repository.save(_entry(title="Updated"))
    assert repository.count() == 1
    assert repository.get("e1").title == "Updated"


def test_ids_returns_all(repository):
    repository.save(_entry(entry_id="a"))
    repository.save(_entry(entry_id="b"))
    assert repository.ids() == {"a", "b"}


def test_round_trip_preserves_body_with_newlines(repository):
    body = "line one\n\nline two\n\nline three"
    repository.save(_entry(body=body))
    fetched = repository.get("e1")
    assert fetched.body == body
