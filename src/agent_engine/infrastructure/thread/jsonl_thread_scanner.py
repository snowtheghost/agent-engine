import contextlib
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import structlog

from agent_engine.application.thread.index.thread_index import ThreadIndex
from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.application.thread.scanner.thread_scanner import ThreadScanner, ThreadScanReport
from agent_engine.infrastructure.thread.chunker import chunk_entries

logger = structlog.get_logger(__name__)

JSONL_SUFFIX = ".jsonl"
CHECKSUMS_FILE_NAME = ".thread_checksums.json"
_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9_\-]+")


class JsonlThreadScanner(ThreadScanner):
    def __init__(
        self,
        threads_dir: Path,
        repository: ThreadRepository,
        index: ThreadIndex,
        checksum_path: Path | None = None,
    ) -> None:
        self._threads_dir = threads_dir
        self._repository = repository
        self._index = index
        self._checksum_path = checksum_path or (threads_dir / CHECKSUMS_FILE_NAME)

    def scan(self, force: bool = False) -> ThreadScanReport:
        self._threads_dir.mkdir(parents=True, exist_ok=True)

        previous = {} if force else self._load_checksums()
        current: dict[str, str] = {}

        indexed = 0
        skipped = 0
        total_chunks = 0

        for path in self._thread_files():
            resume_key = path.stem
            checksum = self._file_checksum(path)
            current[resume_key] = checksum

            if previous.get(resume_key) == checksum:
                skipped += 1
                continue

            thread = self._repository.load(resume_key)
            if thread is None:
                continue

            self._index.delete_by_resume_key(resume_key)
            chunks = chunk_entries(resume_key, thread.entries)
            if chunks:
                self._index.upsert(chunks)
                total_chunks += len(chunks)
            indexed += 1

        removed = 0
        for gone in set(previous) - set(current):
            if self._index.delete_by_resume_key(gone) > 0:
                removed += 1

        self._save_checksums(current)

        report = ThreadScanReport(
            indexed_threads=indexed,
            skipped_unchanged=skipped,
            removed_threads=removed,
            total_threads=len(current),
            total_chunks=self._index.count(),
        )
        logger.info(
            "thread_scan",
            directory=str(self._threads_dir),
            indexed=indexed,
            skipped=skipped,
            removed=removed,
            total_threads=len(current),
            total_chunks=report.total_chunks,
        )
        return report

    def _thread_files(self) -> list[Path]:
        if not self._threads_dir.exists():
            return []
        return sorted(
            path
            for path in self._threads_dir.iterdir()
            if path.is_file() and path.suffix == JSONL_SUFFIX
        )

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


def slugify_resume_key(resume_key: str) -> str:
    cleaned = _SLUG_PATTERN.sub("_", resume_key).strip("_")
    return cleaned or "thread"
