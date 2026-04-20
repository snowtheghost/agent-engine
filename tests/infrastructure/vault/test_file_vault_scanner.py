from datetime import datetime, timezone

import pytest

from agent_engine.core.vault.model.entry import VaultEntry
from agent_engine.infrastructure.vault.file_vault_repository import FileVaultRepository
from agent_engine.infrastructure.vault.file_vault_scanner import FileVaultScanner
from agent_engine.infrastructure.vault.in_memory_vector_index import InMemoryVectorIndex


@pytest.fixture()
def vault_dir(tmp_path):
    directory = tmp_path / "vault"
    directory.mkdir()
    return directory


def _entry(entry_id: str, body: str = "body") -> VaultEntry:
    return VaultEntry(
        entry_id=entry_id,
        kind="note",
        title=f"Title {entry_id}",
        body=body,
        tags=(),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_scan_indexes_all_markdown_files(vault_dir):
    repository = FileVaultRepository(vault_dir)
    for i in range(3):
        repository.save(_entry(f"e{i}", body=f"body {i}"))

    index = InMemoryVectorIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    report = scanner.scan()

    assert report.indexed == 3
    assert report.total == 3
    assert index.ids() == {"e0", "e1", "e2"}


def test_scan_skips_unchanged_on_second_run(vault_dir):
    repository = FileVaultRepository(vault_dir)
    repository.save(_entry("e1"))

    index = InMemoryVectorIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    first = scanner.scan()
    second = scanner.scan()

    assert first.indexed == 1
    assert second.indexed == 0
    assert second.skipped_unchanged == 1


def test_scan_reindexes_when_file_changes(vault_dir):
    repository = FileVaultRepository(vault_dir)
    repository.save(_entry("e1", body="original"))

    index = InMemoryVectorIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    scanner.scan()

    repository.save(_entry("e1", body="updated content about oauth pkce"))
    report = scanner.scan()

    assert report.indexed == 1
    hits = index.search("oauth", limit=5)
    assert hits
    assert hits[0][0] == "e1"


def test_scan_removes_orphaned_index_entries(vault_dir):
    repository = FileVaultRepository(vault_dir)
    repository.save(_entry("e1"))
    repository.save(_entry("e2"))

    index = InMemoryVectorIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    scanner.scan()

    repository.delete("e2")
    report = scanner.scan()

    assert report.removed == 1
    assert index.ids() == {"e1"}


def test_force_rescans_everything(vault_dir):
    repository = FileVaultRepository(vault_dir)
    repository.save(_entry("e1"))

    index = InMemoryVectorIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    scanner.scan()
    report = scanner.scan(force=True)

    assert report.indexed == 1
    assert report.skipped_unchanged == 0


def test_scan_ignores_hidden_files(vault_dir):
    repository = FileVaultRepository(vault_dir)
    repository.save(_entry("e1"))
    (vault_dir / ".ignored.md").write_text("---\nid: x\nkind: y\ntitle: z\n---\n\nbody\n")

    index = InMemoryVectorIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    report = scanner.scan()

    assert report.total == 1
    assert index.ids() == {"e1"}


def test_scan_creates_directory_if_missing(tmp_path):
    directory = tmp_path / "absent"
    index = InMemoryVectorIndex()
    scanner = FileVaultScanner(directory=directory, index=index)
    report = scanner.scan()

    assert directory.exists()
    assert report.total == 0
