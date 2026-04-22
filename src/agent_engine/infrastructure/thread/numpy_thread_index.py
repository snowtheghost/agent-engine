from datetime import datetime

from agent_engine.application.thread.index.thread_index import ThreadIndex
from agent_engine.core.thread.model.chunk import ThreadChunk
from agent_engine.infrastructure.vault.numpy_vector_store import NumpyVectorStore


class NumpyThreadIndex(ThreadIndex):
    def __init__(self, store: NumpyVectorStore) -> None:
        self._store = store

    def upsert(self, chunks: list[ThreadChunk]) -> None:
        if not chunks:
            return
        self._store.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.content for c in chunks],
            metadatas=[self._metadata_for(c) for c in chunks],
        )

    def delete_by_resume_key(self, resume_key: str) -> int:
        existing = self._store.get(where={"resume_key": resume_key})
        ids = existing["ids"]
        if not ids:
            return 0
        self._store.delete(ids=ids)
        return len(ids)

    def search(
        self,
        query: str,
        limit: int,
        resume_key_filter: str | None = None,
    ) -> list[tuple[ThreadChunk, float]]:
        where = {"resume_key": resume_key_filter} if resume_key_filter else None
        results = self._store.query(
            query_texts=[query],
            n_results=limit,
            where=where,
        )
        if not results["ids"] or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        hits: list[tuple[ThreadChunk, float]] = []
        for chunk_id, doc, metadata, dist in zip(ids, documents, metadatas, distances):
            hits.append(
                (
                    ThreadChunk(
                        chunk_id=chunk_id,
                        resume_key=metadata.get("resume_key", ""),
                        entry_index=int(metadata.get("entry_index", 0)),
                        author=metadata.get("author", ""),
                        timestamp=_parse_timestamp(metadata.get("timestamp", "")),
                        content=doc,
                    ),
                    1.0 - dist,
                )
            )
        return hits

    def resume_keys(self) -> set[str]:
        data = self._store.get()
        return {m.get("resume_key", "") for m in data["metadatas"] if m.get("resume_key")}

    def count(self) -> int:
        return self._store.count()

    def close(self) -> None:
        self._store.save()

    @staticmethod
    def _metadata_for(chunk: ThreadChunk) -> dict:
        return {
            "resume_key": chunk.resume_key,
            "entry_index": chunk.entry_index,
            "author": chunk.author,
            "timestamp": chunk.timestamp.isoformat(),
        }


def _parse_timestamp(raw: str) -> datetime:
    if not raw:
        return datetime.fromtimestamp(0)
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.fromtimestamp(0)
