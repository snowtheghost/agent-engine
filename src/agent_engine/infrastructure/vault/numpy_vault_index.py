from agent_engine.application.vault.index.vault_index import VaultIndex
from agent_engine.core.vault.chunk import VaultChunk
from agent_engine.infrastructure.vault.numpy_vector_store import NumpyVectorStore


class NumpyVaultIndex(VaultIndex):

    def __init__(self, store: NumpyVectorStore) -> None:
        self._store = store

    def upsert(self, chunks: list[VaultChunk]) -> None:
        if not chunks:
            return
        self._store.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.content for c in chunks],
            metadatas=[self._metadata_for(c) for c in chunks],
        )

    def delete_by_file(self, file_path: str) -> int:
        existing = self._store.get(where={"file_path": file_path})
        ids = existing["ids"]
        if not ids:
            return 0
        self._store.delete(ids=ids)
        return len(ids)

    def search(
        self,
        query: str,
        limit: int,
        file_filter: str | None = None,
    ) -> list[tuple[VaultChunk, float]]:
        where = {"file_path": file_filter} if file_filter else None
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

        hits: list[tuple[VaultChunk, float]] = []
        for chunk_id, doc, metadata, dist in zip(ids, documents, metadatas, distances):
            chunk = VaultChunk(
                chunk_id=chunk_id,
                file_path=metadata.get("file_path", ""),
                heading=metadata.get("heading", ""),
                content=doc,
                tags=tuple(
                    t.strip()
                    for t in str(metadata.get("tags", "")).split(",")
                    if t.strip()
                ),
            )
            hits.append((chunk, 1.0 - dist))
        return hits

    def file_paths(self) -> set[str]:
        data = self._store.get()
        return {m.get("file_path", "") for m in data["metadatas"] if m.get("file_path")}

    def count(self) -> int:
        return self._store.count()

    def close(self) -> None:
        self._store.save()

    @staticmethod
    def _metadata_for(chunk: VaultChunk) -> dict:
        return {
            "file_path": chunk.file_path,
            "heading": chunk.heading,
            "tags": ",".join(chunk.tags),
        }
