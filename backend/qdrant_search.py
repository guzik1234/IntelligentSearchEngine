import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Local path mode (default, no server needed).
# Set QDRANT_URL in .env to switch to a remote/Docker Qdrant instance.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
QDRANT_PATH = os.getenv("QDRANT_PATH", str(_PROJECT_ROOT / "data" / "qdrant"))
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()

COLLECTION = "movies"
MODEL_NAME = "all-MiniLM-L6-v2"
SIMILARITY_THRESHOLD = 0.20  # cosine; Groq reranker handles fine-sorting

_client = None
_model = None


def _get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient
        if QDRANT_URL:
            _client = QdrantClient(url=QDRANT_URL, timeout=5)
            log.info("Qdrant: remote %s", QDRANT_URL)
        else:
            _client = QdrantClient(path=QDRANT_PATH)
            log.info("Qdrant: local path %s", QDRANT_PATH)
    return _client


def _get_model():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("Loading embedding model %s on %s", MODEL_NAME, device)
        _model = SentenceTransformer(MODEL_NAME, device=device)
    return _model


def preload_model() -> None:
    """Call at startup to avoid cold-start latency on first search."""
    try:
        _get_model()
        log.info("Embedding model ready")
    except Exception as exc:
        log.warning("Could not preload embedding model: %s", exc)


def search(query: str, top_k: int = 40) -> list[dict[str, Any]]:
    """
    Encode `query` and return the top_k most similar movies from Qdrant.
    Returns [] on any error (caller treats it as an empty source).
    """
    try:
        vector = _get_model().encode(query, normalize_embeddings=True).tolist()
        hits = _get_client().search(
            collection_name=COLLECTION,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
            score_threshold=SIMILARITY_THRESHOLD,
        )
        return [{"score": h.score, **h.payload} for h in hits]
    except Exception as exc:
        log.warning("Qdrant search failed: %s", exc)
        return []
