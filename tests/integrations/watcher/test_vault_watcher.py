import asyncio
from pathlib import Path

from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.infrastructure.vault.file_vault_scanner import FileVaultScanner
from agent_engine.infrastructure.vault.in_memory_vault_index import InMemoryVaultIndex
from agent_engine.integrations.watcher.vault_watcher import VaultWatcher


async def _wait_for(condition, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition never met")


def _build_vault(tmp_path: Path):
    directory = tmp_path / "vault"
    directory.mkdir()
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=directory, index=index)
    service = VaultService(directory=directory, index=index, scanner=scanner)
    return service, directory, index


async def test_watcher_indexes_new_file(tmp_path):
    service, directory, index = _build_vault(tmp_path)
    watcher = VaultWatcher(directory=directory, vault=service)
    await watcher.start()
    try:
        await asyncio.sleep(0.3)
        path = directory / "note.md"
        path.write_text(
            "## Topic\nSome new content long enough to become a vault chunk.\n",
            encoding="utf-8",
        )
        await _wait_for(lambda: index.file_paths() == {"note.md"})
    finally:
        await watcher.stop()


async def test_watcher_reindexes_modified_file(tmp_path):
    service, directory, index = _build_vault(tmp_path)
    path = directory / "note.md"
    path.write_text("## A\nOriginal content long enough to chunk.\n", encoding="utf-8")
    service.ingest(path)

    watcher = VaultWatcher(directory=directory, vault=service)
    await watcher.start()
    try:
        await asyncio.sleep(0.3)
        path.write_text(
            "## A\nUpdated content mentioning pineapple long enough to chunk.\n",
            encoding="utf-8",
        )
        await _wait_for(lambda: bool(index.search("pineapple", limit=3)))
    finally:
        await watcher.stop()


async def test_watcher_removes_deleted_file(tmp_path):
    service, directory, index = _build_vault(tmp_path)
    path = directory / "note.md"
    path.write_text("## A\nContent long enough to chunk here now.\n", encoding="utf-8")
    service.ingest(path)
    assert index.file_paths() == {"note.md"}

    watcher = VaultWatcher(directory=directory, vault=service)
    await watcher.start()
    try:
        await asyncio.sleep(0.3)
        path.unlink()
        await _wait_for(lambda: index.file_paths() == set())
    finally:
        await watcher.stop()


async def test_watcher_ignores_non_markdown(tmp_path):
    service, directory, index = _build_vault(tmp_path)
    watcher = VaultWatcher(directory=directory, vault=service)
    await watcher.start()
    try:
        await asyncio.sleep(0.3)
        (directory / "note.txt").write_text("plain text, not tracked", encoding="utf-8")
        await asyncio.sleep(1.0)
        assert index.file_paths() == set()
    finally:
        await watcher.stop()


async def test_watcher_ignores_hidden_paths(tmp_path):
    service, directory, index = _build_vault(tmp_path)
    hidden = directory / ".store"
    hidden.mkdir()
    watcher = VaultWatcher(directory=directory, vault=service)
    await watcher.start()
    try:
        await asyncio.sleep(0.3)
        (hidden / "x.md").write_text(
            "## A\nContent long enough to chunk here inside hidden.\n",
            encoding="utf-8",
        )
        await asyncio.sleep(1.0)
        assert index.file_paths() == set()
    finally:
        await watcher.stop()
