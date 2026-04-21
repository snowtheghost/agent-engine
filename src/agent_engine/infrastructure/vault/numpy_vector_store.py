import json
from collections.abc import Callable
from pathlib import Path
from threading import Lock

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


def _matches_filter(metadata: dict, where: dict) -> bool:
    if not where:
        return True

    if "$and" in where:
        return all(_matches_filter(metadata, cond) for cond in where["$and"])

    if "$or" in where:
        return any(_matches_filter(metadata, cond) for cond in where["$or"])

    for k, v in where.items():
        actual = metadata.get(k, "")
        if isinstance(v, dict):
            if "$contains" in v:
                if v["$contains"] not in str(actual):
                    return False
            elif "$ne" in v:
                if actual == v["$ne"]:
                    return False
        else:
            if actual != v:
                return False
    return True


class NumpyVectorStore:

    def __init__(
        self,
        store_dir: Path | str,
        name: str,
        embed_fn: Callable[[list[str]], np.ndarray],
        embedding_dim: int = 768,
        query_embed_fn: Callable[[list[str]], np.ndarray] | None = None,
    ) -> None:
        self._store_dir = Path(store_dir)
        self._name = name
        self._embed_fn = embed_fn
        self._query_embed_fn = query_embed_fn or embed_fn
        self._dim = embedding_dim
        self._lock = Lock()

        self._store_dir.mkdir(parents=True, exist_ok=True)

        self._ids: list[str] = []
        self._documents: list[str] = []
        self._metadatas: list[dict] = []
        self._embeddings: np.ndarray = np.empty((0, self._dim), dtype=np.float32)

        self._load()

    @property
    def _emb_path(self) -> Path:
        return self._store_dir / f"{self._name}_embeddings.npy"

    @property
    def _index_path(self) -> Path:
        return self._store_dir / f"{self._name}_index.json"

    def _load(self) -> None:
        if self._index_path.exists() and self._emb_path.exists():
            try:
                with open(self._index_path) as f:
                    data = json.load(f)
                self._ids = data.get("ids", [])
                self._documents = data.get("documents", [])
                self._metadatas = data.get("metadatas", [])
                self._embeddings = np.load(str(self._emb_path))

                n = len(self._ids)
                if self._embeddings.shape[0] != n:
                    logger.warning(
                        "vector_store_inconsistent",
                        name=self._name,
                        ids=n,
                        embs=self._embeddings.shape[0],
                    )
                    self._clear_memory()
                    return

                if self._embeddings.ndim == 2 and self._embeddings.shape[1] != self._dim:
                    logger.warning(
                        "vector_store_dimension_mismatch",
                        name=self._name,
                        stored=self._embeddings.shape[1],
                        expected=self._dim,
                    )
                    self._clear_memory()
                    return

                logger.debug(
                    "vector_store_loaded",
                    name=self._name,
                    count=n,
                )
            except Exception:
                logger.warning(
                    "vector_store_load_failed",
                    name=self._name,
                )
                self._clear_memory()
        else:
            self._clear_memory()

    def _clear_memory(self) -> None:
        self._ids = []
        self._documents = []
        self._metadatas = []
        self._embeddings = np.empty((0, self._dim), dtype=np.float32)

    def save(self) -> None:
        tmp_index = self._index_path.with_suffix(".tmp")
        with open(tmp_index, "w") as f:
            json.dump(
                {
                    "ids": self._ids,
                    "documents": self._documents,
                    "metadatas": self._metadatas,
                },
                f,
            )
        tmp_index.rename(self._index_path)

        tmp_emb = self._emb_path.with_suffix(".tmp.npy")
        np.save(str(tmp_emb), self._embeddings)
        tmp_emb.rename(self._emb_path)

    def count(self) -> int:
        with self._lock:
            return len(self._ids)

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return

        new_embeddings = self._embed_fn(documents)

        with self._lock:
            id_map = {id_: i for i, id_ in enumerate(self._ids)}

            for j, id_ in enumerate(ids):
                if id_ in id_map:
                    idx = id_map[id_]
                    self._documents[idx] = documents[j]
                    self._metadatas[idx] = metadatas[j]
                    self._embeddings[idx] = new_embeddings[j]
                else:
                    self._ids.append(id_)
                    self._documents.append(documents[j])
                    self._metadatas.append(metadatas[j])
                    self._embeddings = np.vstack(
                        [self._embeddings, new_embeddings[j : j + 1]]
                    )
                    id_map[id_] = len(self._ids) - 1

            self.save()

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return

        with self._lock:
            id_set = set(ids)
            keep = [i for i, id_ in enumerate(self._ids) if id_ not in id_set]

            if len(keep) == len(self._ids):
                return

            self._ids = [self._ids[i] for i in keep]
            self._documents = [self._documents[i] for i in keep]
            self._metadatas = [self._metadatas[i] for i in keep]

            if keep:
                self._embeddings = self._embeddings[keep]
            else:
                self._embeddings = np.empty((0, self._dim), dtype=np.float32)

            self.save()

    def get(
        self,
        ids: list[str] | None = None,
        where: dict | None = None,
    ) -> dict[str, list]:
        with self._lock:
            result_ids = []
            result_docs = []
            result_metas = []

            for i, id_ in enumerate(self._ids):
                if ids is not None and id_ not in ids:
                    continue
                if where is not None and not _matches_filter(self._metadatas[i], where):
                    continue
                result_ids.append(id_)
                result_docs.append(self._documents[i])
                result_metas.append(self._metadatas[i])

            return {
                "ids": result_ids,
                "documents": result_docs,
                "metadatas": result_metas,
            }

    def query(
        self,
        query_texts: list[str],
        n_results: int = 10,
        where: dict | None = None,
    ) -> dict[str, list[list]]:
        if not query_texts:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        query_embeddings = self._query_embed_fn(query_texts)

        all_ids = []
        all_docs = []
        all_metas = []
        all_dists = []

        with self._lock:
            for q_emb in query_embeddings:
                if len(self._ids) == 0:
                    all_ids.append([])
                    all_docs.append([])
                    all_metas.append([])
                    all_dists.append([])
                    continue

                if where:
                    mask = [
                        _matches_filter(self._metadatas[i], where)
                        for i in range(len(self._ids))
                    ]
                    indices = [i for i, m in enumerate(mask) if m]
                else:
                    indices = list(range(len(self._ids)))

                if not indices:
                    all_ids.append([])
                    all_docs.append([])
                    all_metas.append([])
                    all_dists.append([])
                    continue

                filtered_embs = self._embeddings[indices]
                similarities = np.dot(filtered_embs, q_emb)

                n = min(n_results, len(indices))
                if n >= len(indices):
                    top_k = np.argsort(-similarities)
                else:
                    top_k = np.argpartition(-similarities, n)[:n]
                    top_k = top_k[np.argsort(-similarities[top_k])]

                q_ids = [self._ids[indices[k]] for k in top_k]
                q_docs = [self._documents[indices[k]] for k in top_k]
                q_metas = [self._metadatas[indices[k]] for k in top_k]
                q_dists = [float(1.0 - similarities[k]) for k in top_k]

                all_ids.append(q_ids)
                all_docs.append(q_docs)
                all_metas.append(q_metas)
                all_dists.append(q_dists)

        return {
            "ids": all_ids,
            "documents": all_docs,
            "metadatas": all_metas,
            "distances": all_dists,
        }

    def reset(self) -> None:
        with self._lock:
            self._clear_memory()
            if self._emb_path.exists():
                self._emb_path.unlink()
            if self._index_path.exists():
                self._index_path.unlink()
