import pytest

from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.infrastructure.vault.file_vault_scanner import FileVaultScanner
from agent_engine.infrastructure.vault.in_memory_vault_index import InMemoryVaultIndex


@pytest.fixture()
def vault(tmp_path):
    directory = tmp_path / "vault"
    directory.mkdir()
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=directory, index=index)
    return VaultService(directory=directory, index=index, scanner=scanner)


def test_write_creates_markdown_file(vault, tmp_path):
    path = vault.write(title="Use WAL", content="Better concurrency story.")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "# Use WAL" in text
    assert "Better concurrency story." in text


def test_write_then_search_finds_file(vault):
    vault.write(title="Auth flow", content="oauth pkce session management tokens.")
    hits = vault.search("oauth", limit=5)
    assert hits
    assert hits[0].chunk.file_path.endswith(".md")


def test_search_includes_filesystem_path(vault, tmp_path):
    path = vault.write(title="Note", content="content with unique keyword pineapple inside.")
    hits = vault.search("pineapple", limit=5)
    assert hits
    assert hits[0].path == path


def test_recall_returns_full_markdown(vault):
    path = vault.write(title="Something", content="Body text here with decent length.")
    rel = path.name
    body = vault.recall(rel)
    assert body is not None
    assert "Body text here" in body
    assert body.startswith("---\n")


def test_recall_missing_returns_none(vault):
    assert vault.recall("does-not-exist.md") is None


def test_write_into_subdirectory(vault, tmp_path):
    path = vault.write(
        title="Decision",
        content="Use microservices for the auth layer please.",
        subdirectory="Architecture",
    )
    assert path.parent.name == "Architecture"
    hits = vault.search("microservices auth", limit=5)
    assert hits
    assert hits[0].chunk.file_path.startswith("Architecture/")


def test_write_deduplicates_filenames(vault):
    first = vault.write(title="Duplicate Title", content="First body long enough to chunk.")
    second = vault.write(title="Duplicate Title", content="Second body long enough to chunk.")
    assert first != second
    assert first.exists() and second.exists()


def test_tags_surface_in_search_results(vault):
    vault.write(
        title="Tagged",
        content="Content about deployment pipeline and release strategy here.",
        tags=("deploy", "ops"),
    )
    hits = vault.search("deployment pipeline", limit=5)
    assert hits
    assert "deploy" in hits[0].chunk.tags
