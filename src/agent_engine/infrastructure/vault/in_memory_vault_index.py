import math
import re
from collections import Counter

from agent_engine.application.vault.index.vault_index import VaultIndex
from agent_engine.core.vault.chunk import VaultChunk

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


def _vectorize(text: str) -> Counter[str]:
    return Counter(_tokenize(text))


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = set(a) & set(b)
    dot = sum(a[token] * b[token] for token in overlap)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVaultIndex(VaultIndex):

    def __init__(self) -> None:
        self._chunks: dict[str, VaultChunk] = {}
        self._vectors: dict[str, Counter[str]] = {}

    def upsert(self, chunks: list[VaultChunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
            self._vectors[chunk.chunk_id] = _vectorize(chunk.content)

    def delete_by_file(self, file_path: str) -> int:
        ids = [cid for cid, c in self._chunks.items() if c.file_path == file_path]
        for cid in ids:
            self._chunks.pop(cid, None)
            self._vectors.pop(cid, None)
        return len(ids)

    def search(
        self,
        query: str,
        limit: int,
        file_filter: str | None = None,
    ) -> list[tuple[VaultChunk, float]]:
        query_vector = _vectorize(query)
        scored: list[tuple[VaultChunk, float]] = []
        for chunk_id, vector in self._vectors.items():
            chunk = self._chunks[chunk_id]
            if file_filter is not None and chunk.file_path != file_filter:
                continue
            score = _cosine(query_vector, vector)
            if score > 0.0:
                scored.append((chunk, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    def file_paths(self) -> set[str]:
        return {c.file_path for c in self._chunks.values()}

    def count(self) -> int:
        return len(self._chunks)

    def close(self) -> None:
        self._chunks.clear()
        self._vectors.clear()
