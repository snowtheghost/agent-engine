from agent_engine.application.vault.index.vector_index import VectorIndex
from agent_engine.infrastructure.vault.numpy_vector_store import NumpyVectorStore


class PersistentVectorIndex(VectorIndex):

    def __init__(self, store: NumpyVectorStore) -> None:
        self._store = store

    def upsert(self, entry_id: str, text: str) -> None:
        self._store.upsert(
            ids=[entry_id],
            documents=[text],
            metadatas=[{"entry_id": entry_id}],
        )

    def remove(self, entry_id: str) -> None:
        self._store.delete(ids=[entry_id])

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        results = self._store.query(
            query_texts=[query],
            n_results=limit,
        )
        if not results["ids"] or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        distances = results["distances"][0]
        return list(zip(ids, [1.0 - d for d in distances]))

    def ids(self) -> set[str]:
        data = self._store.get()
        return set(data["ids"])

    def close(self) -> None:
        self._store.save()
