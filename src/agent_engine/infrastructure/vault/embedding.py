import numpy as np
import structlog

logger = structlog.get_logger(__name__)

MODEL_ID = "nomic-ai/nomic-embed-text-v1.5"
EMBEDDING_DIM = 768

QUERY_PREFIX = "search_query: "
DOCUMENT_PREFIX = "search_document: "

_model = None


def _get_model() -> "SentenceTransformer":  # noqa: F821
    global _model
    if _model is not None:
        return _model

    from sentence_transformers import SentenceTransformer

    logger.info("embedding_model_loading", model_id=MODEL_ID, device="cpu")
    _model = SentenceTransformer(
        MODEL_ID,
        trust_remote_code=True,
        device="cpu",
        model_kwargs={"dtype": "float32"},
    )
    logger.info("embedding_model_ready", model_id=MODEL_ID, dim=EMBEDDING_DIM, device="cpu")
    return _model


def _embed(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype(np.float32)


def embed_documents(texts: list[str]) -> np.ndarray:
    return _embed([DOCUMENT_PREFIX + t for t in texts])


def embed_queries(texts: list[str]) -> np.ndarray:
    return _embed([QUERY_PREFIX + t for t in texts])
