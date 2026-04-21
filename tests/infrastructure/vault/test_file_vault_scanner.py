import pytest

from agent_engine.infrastructure.vault.file_vault_scanner import FileVaultScanner
from agent_engine.infrastructure.vault.in_memory_vault_index import InMemoryVaultIndex


@pytest.fixture()
def vault_dir(tmp_path):
    directory = tmp_path / "vault"
    directory.mkdir()
    return directory


def _write(directory, rel: str, body: str) -> None:
    path = directory / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_scan_indexes_chunks_from_markdown_files(vault_dir):
    _write(
        vault_dir,
        "a.md",
        "## S1\nAuthentication oauth content long enough to chunk.\n",
    )
    _write(
        vault_dir,
        "Nested/b.md",
        "## S2\nDatabase migration content long enough to chunk.\n",
    )
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)

    report = scanner.scan()

    assert report.indexed_files == 2
    assert report.total_files == 2
    assert report.total_chunks >= 2
    assert index.file_paths() == {"a.md", "Nested/b.md"}


def test_scan_skips_unchanged_on_second_run(vault_dir):
    _write(vault_dir, "a.md", "## S\nSome content long enough to become a chunk.\n")
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)

    first = scanner.scan()
    second = scanner.scan()

    assert first.indexed_files == 1
    assert second.indexed_files == 0
    assert second.skipped_unchanged == 1


def test_scan_reindexes_when_file_changes(vault_dir):
    _write(vault_dir, "a.md", "## S\nOriginal content long enough for chunking.\n")
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    scanner.scan()

    _write(vault_dir, "a.md", "## S\nUpdated content mentioning oauth pkce flows.\n")
    scanner.scan()

    hits = index.search("oauth", limit=5)
    assert hits
    assert hits[0][0].file_path == "a.md"


def test_scan_removes_chunks_when_file_deleted(vault_dir):
    _write(vault_dir, "a.md", "## S\nKeep content long enough to chunk here please.\n")
    _write(vault_dir, "b.md", "## S\nRemove content long enough to chunk here too.\n")
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    scanner.scan()

    (vault_dir / "b.md").unlink()
    report = scanner.scan()

    assert report.removed_files == 1
    assert index.file_paths() == {"a.md"}


def test_force_reindexes_everything(vault_dir):
    _write(vault_dir, "a.md", "## S\nContent long enough to chunk into a section.\n")
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)

    scanner.scan()
    report = scanner.scan(force=True)

    assert report.indexed_files == 1
    assert report.skipped_unchanged == 0


def test_scan_ignores_hidden_directories(vault_dir):
    _write(vault_dir, "a.md", "## S\nVisible content long enough to chunk here.\n")
    _write(vault_dir, ".store/b.md", "## S\nHidden content long enough to chunk.\n")
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=vault_dir, index=index)
    report = scanner.scan()

    assert report.total_files == 1
    assert index.file_paths() == {"a.md"}


def test_scan_creates_directory_if_missing(tmp_path):
    directory = tmp_path / "absent"
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=directory, index=index)
    report = scanner.scan()

    assert directory.exists()
    assert report.total_files == 0
