import contextlib
import os
import re
import tempfile
from pathlib import Path

import structlog

from agent_engine.application.vault.index.vault_index import VaultIndex
from agent_engine.application.vault.scanner.vault_scanner import VaultScanner
from agent_engine.core.vault.chunk import VaultSearchHit
from agent_engine.infrastructure.vault.chunker import chunk_markdown

logger = structlog.get_logger(__name__)


_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9]+")
_VAULT_FILE_SUFFIX = ".md"


class VaultService:

    def __init__(
        self,
        directory: Path,
        index: VaultIndex,
        scanner: VaultScanner,
    ) -> None:
        self._directory = directory
        self._index = index
        self._scanner = scanner

    def write(
        self,
        *,
        title: str,
        content: str,
        tags: tuple[str, ...] = (),
        subdirectory: str | None = None,
    ) -> Path:
        target_dir = self._directory
        if subdirectory:
            target_dir = target_dir / subdirectory
        target_dir.mkdir(parents=True, exist_ok=True)

        path = self._unique_path(target_dir, title)
        text = self._format_markdown(title=title, content=content, tags=tags)
        _atomic_write(path, text)

        rel = str(path.relative_to(self._directory))
        chunks = chunk_markdown(text, rel)
        if chunks:
            self._index.delete_by_file(rel)
            self._index.upsert(chunks)

        logger.info(
            "vault_write",
            path=str(path),
            chunks=len(chunks),
            title=title,
        )
        return path

    def search(
        self,
        query: str,
        limit: int = 5,
        file_filter: str | None = None,
    ) -> list[VaultSearchHit]:
        raw = self._index.search(query, limit, file_filter=file_filter)
        hits: list[VaultSearchHit] = []
        for chunk, score in raw:
            hits.append(
                VaultSearchHit(
                    chunk=chunk,
                    score=score,
                    path=self._directory / chunk.file_path,
                )
            )
        logger.info("vault_search", query_preview=query[:120], result_count=len(hits))
        return hits

    def recall(self, file_path: str) -> str | None:
        candidate = self._resolve_path(file_path)
        if candidate is None or not candidate.is_file():
            return None
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def count(self) -> int:
        return self._index.count()

    def files(self) -> set[str]:
        return self._index.file_paths()

    def rescan(self, force: bool = False):
        return self._scanner.scan(force=force)

    @staticmethod
    def _format_markdown(
        *,
        title: str,
        content: str,
        tags: tuple[str, ...],
    ) -> str:
        frontmatter_lines = ["---"]
        if tags:
            tag_literal = ", ".join(tags)
            frontmatter_lines.append(f"tags: [{tag_literal}]")
        frontmatter_lines.append("---")
        body_lines = [f"# {title}", "", content.rstrip()]
        return "\n".join(frontmatter_lines + [""] + body_lines) + "\n"

    def _unique_path(self, target_dir: Path, title: str) -> Path:
        base = _slugify(title) or "entry"
        candidate = target_dir / f"{base}{_VAULT_FILE_SUFFIX}"
        suffix = 2
        while candidate.exists():
            candidate = target_dir / f"{base}-{suffix}{_VAULT_FILE_SUFFIX}"
            suffix += 1
        return candidate

    def _resolve_path(self, file_path: str) -> Path | None:
        if not file_path:
            return None
        as_path = Path(file_path)
        if as_path.is_absolute():
            try:
                as_path.relative_to(self._directory)
            except ValueError:
                return None
            return as_path
        return (self._directory / file_path).resolve()


def _slugify(title: str) -> str:
    cleaned = _SLUG_PATTERN.sub("-", title).strip("-")
    return cleaned[:80]


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
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
