import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path

import structlog

from agent_engine.application.vault.index.vector_index import VectorIndex
from agent_engine.application.vault.scanner.vault_scanner import ScanReport, VaultScanner
from agent_engine.infrastructure.vault.file_vault_repository import VAULT_FILE_SUFFIX
from agent_engine.infrastructure.vault.markdown_frontmatter import parse_entry


logger = structlog.get_logger(__name__)

CHECKSUMS_FILE_NAME = ".vault_checksums.json"


class FileVaultScanner(VaultScanner):

    def __init__(
        self,
        directory: Path,
        index: VectorIndex,
        checksum_path: Path | None = None,
    ) -> None:
        self._directory = directory
        self._index = index
        self._checksum_path = checksum_path or (directory / CHECKSUMS_FILE_NAME)

    def scan(self, force: bool = False) -> ScanReport:
        self._directory.mkdir(parents=True, exist_ok=True)

        previous = {} if force else self._load_checksums()
        current_checksums: dict[str, str] = {}
        current_ids: set[str] = set()

        indexed = 0
        skipped = 0

        for path in self._markdown_files():
            checksum = self._file_checksum(path)
            key = self._relative_key(path)
            current_checksums[key] = checksum

            entry = self._read_entry(path)
            if entry is None:
                continue
            current_ids.add(entry.entry_id)

            if previous.get(key) == checksum:
                skipped += 1
                continue

            self._index.upsert(entry.entry_id, self._index_text(entry))
            indexed += 1

        removed = 0
        for entry_id in self._index.ids() - current_ids:
            self._index.remove(entry_id)
            removed += 1

        self._save_checksums(current_checksums)

        report = ScanReport(
            indexed=indexed,
            skipped_unchanged=skipped,
            removed=removed,
            total=len(current_ids),
        )
        logger.info(
            "vault_scan",
            directory=str(self._directory),
            indexed=indexed,
            skipped=skipped,
            removed=removed,
            total=len(current_ids),
        )
        return report

    def _markdown_files(self) -> list[Path]:
        if not self._directory.exists():
            return []
        return sorted(
            path
            for path in self._directory.rglob(f"*{VAULT_FILE_SUFFIX}")
            if path.is_file() and not path.name.startswith(".")
        )

    def _relative_key(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._directory))
        except ValueError:
            return str(path)

    @staticmethod
    def _file_checksum(path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    @staticmethod
    def _read_entry(path: Path):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return parse_entry(text)

    @staticmethod
    def _index_text(entry) -> str:
        return f"{entry.title}\n{entry.body}"

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
