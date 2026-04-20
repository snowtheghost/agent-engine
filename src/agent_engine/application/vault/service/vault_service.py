import uuid
from datetime import datetime, timezone

import structlog

from agent_engine.application.vault.index.vector_index import VectorIndex
from agent_engine.application.vault.repository.vault_repository import VaultRepository
from agent_engine.core.vault.model.entry import VaultEntry, VaultSearchHit

logger = structlog.get_logger(__name__)


class VaultService:

    def __init__(
        self,
        repository: VaultRepository,
        index: VectorIndex,
    ) -> None:
        self._repository = repository
        self._index = index

    def write(
        self,
        *,
        kind: str,
        title: str,
        body: str,
        tags: tuple[str, ...] = (),
    ) -> VaultEntry:
        entry = VaultEntry(
            entry_id=str(uuid.uuid4()),
            kind=kind,
            title=title,
            body=body,
            tags=tags,
            created_at=datetime.now(timezone.utc),
        )
        path = self._repository.save(entry)
        self._index.upsert(entry.entry_id, f"{entry.title}\n{entry.body}")
        logger.info(
            "vault_write",
            entry_id=entry.entry_id,
            kind=entry.kind,
            title=entry.title,
            tag_count=len(entry.tags),
            path=str(path),
        )
        return entry

    def search(self, query: str, limit: int = 5) -> list[VaultSearchHit]:
        raw = self._index.search(query, limit)
        hits: list[VaultSearchHit] = []
        for entry_id, score in raw:
            entry = self._repository.get(entry_id)
            path = self._repository.path_for(entry_id)
            if entry is None or path is None:
                continue
            hits.append(VaultSearchHit(entry=entry, score=score, path=path))
        logger.info("vault_search", query_preview=query[:120], result_count=len(hits))
        return hits

    def recall(self, entry_id: str) -> VaultEntry | None:
        return self._repository.get(entry_id)

    def list(self, limit: int = 100) -> list[VaultEntry]:
        return self._repository.list(limit)

    def delete(self, entry_id: str) -> bool:
        removed = self._repository.delete(entry_id)
        if removed:
            self._index.remove(entry_id)
        return removed

    def count(self) -> int:
        return self._repository.count()
