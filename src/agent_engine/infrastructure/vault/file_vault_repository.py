from __future__ import annotations

import os
import tempfile
from pathlib import Path

from agent_engine.application.vault.repository.vault_repository import VaultRepository
from agent_engine.core.vault.model.entry import VaultEntry
from agent_engine.infrastructure.vault.markdown_frontmatter import format_entry, parse_entry


VAULT_FILE_SUFFIX = ".md"


class FileVaultRepository(VaultRepository):

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._directory

    def save(self, entry: VaultEntry) -> Path:
        path = self._path_for_id(entry.entry_id)
        self._directory.mkdir(parents=True, exist_ok=True)
        text = format_entry(entry)
        _atomic_write(path, text)
        return path

    def get(self, entry_id: str) -> VaultEntry | None:
        path = self._path_for_id(entry_id)
        if not path.is_file():
            return None
        return _read_entry(path)

    def path_for(self, entry_id: str) -> Path | None:
        path = self._path_for_id(entry_id)
        return path if path.is_file() else None

    def list(self, limit: int = 100) -> list[VaultEntry]:
        entries = [
            entry
            for entry in (_read_entry(path) for path in self._markdown_files())
            if entry is not None
        ]
        entries.sort(key=lambda entry: entry.created_at, reverse=True)
        return entries[:limit]

    def delete(self, entry_id: str) -> bool:
        path = self._path_for_id(entry_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def count(self) -> int:
        return sum(1 for _ in self._markdown_files())

    def ids(self) -> set[str]:
        result: set[str] = set()
        for path in self._markdown_files():
            entry = _read_entry(path)
            if entry is not None:
                result.add(entry.entry_id)
        return result

    def _markdown_files(self) -> list[Path]:
        if not self._directory.exists():
            return []
        return [
            path
            for path in self._directory.rglob(f"*{VAULT_FILE_SUFFIX}")
            if path.is_file() and not path.name.startswith(".")
        ]

    def _path_for_id(self, entry_id: str) -> Path:
        return self._directory / f"{entry_id}{VAULT_FILE_SUFFIX}"


def _read_entry(path: Path) -> VaultEntry | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return parse_entry(text)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    closed = False
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        closed = True
        os.replace(tmp_path, str(path))
    except BaseException:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
