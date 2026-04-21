import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path

import structlog

from agent_engine.application.vault.index.vault_index import VaultIndex
from agent_engine.application.vault.scanner.vault_scanner import ScanReport, VaultScanner
from agent_engine.infrastructure.vault.chunker import chunk_markdown

logger = structlog.get_logger(__name__)

VAULT_FILE_SUFFIX = ".md"
CHECKSUMS_FILE_NAME = ".vault_checksums.json"


class FileVaultScanner(VaultScanner):

    def __init__(
        self,
        directory: Path,
        index: VaultIndex,
        checksum_path: Path | None = None,
    ) -> None:
        self._directory = directory
        self._index = index
        self._checksum_path = checksum_path or (directory / CHECKSUMS_FILE_NAME)

    def scan(self, force: bool = False) -> ScanReport:
        self._directory.mkdir(parents=True, exist_ok=True)

        previous = {} if force else self._load_checksums()
        current: dict[str, str] = {}

        indexed = 0
        skipped = 0
        total_chunks = 0

        for path in self._markdown_files():
            rel = self._relative_key(path)
            checksum = self._file_checksum(path)
            current[rel] = checksum

            if previous.get(rel) == checksum:
                skipped += 1
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            self._index.delete_by_file(rel)
            chunks = chunk_markdown(text, rel)
            if chunks:
                self._index.upsert(chunks)
                total_chunks += len(chunks)
            indexed += 1

        removed_files = 0
        for gone in set(previous) - set(current):
            if self._index.delete_by_file(gone) > 0:
                removed_files += 1

        self._save_checksums(current)

        report = ScanReport(
            indexed_files=indexed,
            skipped_unchanged=skipped,
            removed_files=removed_files,
            total_files=len(current),
            total_chunks=self._index.count(),
        )
        logger.info(
            "vault_scan",
            directory=str(self._directory),
            indexed=indexed,
            skipped=skipped,
            removed=removed_files,
            total_files=len(current),
            total_chunks=report.total_chunks,
        )
        return report

    def _markdown_files(self) -> list[Path]:
        if not self._directory.exists():
            return []
        return sorted(
            path
            for path in self._directory.rglob(f"*{VAULT_FILE_SUFFIX}")
            if path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(self._directory).parts)
        )

    def _relative_key(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._directory))
        except ValueError:
            return str(path)

    @staticmethod
    def _file_checksum(path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    def _load_checksums(self) -> dict[str, str]:
        if not self._checksum_path.is_file():
            return {}
        try:
            return json.loads(self._checksum_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_checksums(self, checksums: dict[str, str]) -> None:
        self._checksum_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(checksums, indent=2, sort_keys=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(self._checksum_path.parent), suffix=".tmp")
        closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            closed = True
            os.replace(tmp_path, str(self._checksum_path))
        except BaseException:
            if not closed:
                with contextlib.suppress(OSError):
                    os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
