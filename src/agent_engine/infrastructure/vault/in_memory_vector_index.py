import math
import re
from collections import Counter

from agent_engine.application.vault.index.vector_index import VectorIndex

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


class InMemoryVectorIndex(VectorIndex):

    def __init__(self) -> None:
        self._vectors: dict[str, Counter[str]] = {}

    def upsert(self, entry_id: str, text: str) -> None:
        self._vectors[entry_id] = _vectorize(text)

    def remove(self, entry_id: str) -> None:
        self._vectors.pop(entry_id, None)

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        query_vector = _vectorize(query)
        scored: list[tuple[str, float]] = []
        for entry_id, vector in self._vectors.items():
            score = _cosine(query_vector, vector)
            if score > 0.0:
                scored.append((entry_id, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    def ids(self) -> set[str]:
        return set(self._vectors.keys())

    def close(self) -> None:
        self._vectors.clear()
