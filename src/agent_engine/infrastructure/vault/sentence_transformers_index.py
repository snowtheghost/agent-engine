import pickle
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from agent_engine.application.vault.index.vector_index import VectorIndex

logger = structlog.get_logger(__name__)


class SentenceTransformersIndex(VectorIndex):

    def __init__(self, model_name: str, storage_path: Path) -> None:
        self._model_name = model_name
        self._storage_path = storage_path
        self._model: Any | None = None
        self._embeddings: dict[str, np.ndarray] = {}
        self._load()

    def _ensure_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            logger.info("vector_index_model_loaded", model=self._model_name)
        return self._model

    def _load(self) -> None:
        if not self._storage_path.is_file():
            return
        with self._storage_path.open("rb") as fh:
            payload = pickle.load(fh)
        if payload.get("model_name") != self._model_name:
            logger.warning(
                "vector_index_model_mismatch",
                stored=payload.get("model_name"),
                requested=self._model_name,
            )
            return
        self._embeddings = payload.get("embeddings", {})
        logger.info("vector_index_loaded", entries=len(self._embeddings))

    def _persist(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._storage_path.open("wb") as fh:
            pickle.dump(
                {"model_name": self._model_name, "embeddings": self._embeddings}, fh
            )

    def upsert(self, entry_id: str, text: str) -> None:
        model = self._ensure_model()
        embedding = model.encode(text, normalize_embeddings=True)
        self._embeddings[entry_id] = np.asarray(embedding, dtype=np.float32)
        self._persist()

    def remove(self, entry_id: str) -> None:
        if self._embeddings.pop(entry_id, None) is not None:
            self._persist()

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        if not self._embeddings:
            return []
        model = self._ensure_model()
        query_embedding = np.asarray(
            model.encode(query, normalize_embeddings=True),
            dtype=np.float32,
        )
        scored: list[tuple[str, float]] = []
        for entry_id, embedding in self._embeddings.items():
            score = float(np.dot(query_embedding, embedding))
            scored.append((entry_id, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:limit]

    def ids(self) -> set[str]:
        return set(self._embeddings.keys())

    def close(self) -> None:
        self._persist()
        self._embeddings.clear()
        self._model = None
