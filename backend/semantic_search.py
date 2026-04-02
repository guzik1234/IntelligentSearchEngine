import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

EMBEDDINGS_MODEL = "all-MiniLM-L6-v2"
_EMBEDDINGS_FILE = "embeddings.npy"
_METADATA_FILE = "embeddings_meta.json"


def _text_for_movie(
    title: str,
    genres: str,
    description: str | None,
    plot: str | None,
) -> str:
    parts = [title, genres.replace("|", " ")]
    if description:
        parts.append(description)
    if plot:
        parts.append(plot)
    return " ".join(parts)


def _cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10
    return (matrix / norms) @ q


def _build_and_cache(db_path: Path) -> tuple[np.ndarray, list[dict[str, Any]]]:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT movieId, title, genres, description, plot FROM movies")
        db_rows = cur.fetchall()

    metadata: list[dict[str, Any]] = []
    texts: list[str] = []
    for movie_id, title, genres, description, plot in db_rows:
        texts.append(_text_for_movie(title, genres or "", description, plot))
        metadata.append(
            {
                "movieId": movie_id,
                "title": title,
                "genres": genres or "",
                "description": description,
                "plot": plot,
            }
        )

    model = SentenceTransformer(EMBEDDINGS_MODEL)
    embeddings: np.ndarray = model.encode(
        texts, show_progress_bar=True, batch_size=64, convert_to_numpy=True
    )

    db_dir = db_path.parent
    np.save(str(db_dir / _EMBEDDINGS_FILE), embeddings)
    with open(db_dir / _METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)

    return embeddings, metadata


class SemanticSearchEngine:
    def __init__(self) -> None:
        self._embeddings: np.ndarray | None = None
        self._metadata: list[dict[str, Any]] | None = None
        self._model: Any = None
        self._ready = False
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------
    # Blocking load – call via asyncio.to_thread
    # -------------------------------------------------------------------
    def _load_sync(self, db_path: Path) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        db_dir = db_path.parent
        emb_path = db_dir / _EMBEDDINGS_FILE
        meta_path = db_dir / _METADATA_FILE

        if emb_path.exists() and meta_path.exists():
            self._embeddings = np.load(str(emb_path))
            with open(meta_path, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)
        else:
            self._embeddings, self._metadata = _build_and_cache(db_path)

        self._model = SentenceTransformer(EMBEDDINGS_MODEL)
        self._ready = True

    # -------------------------------------------------------------------
    # Async-safe initializer (idempotent)
    # -------------------------------------------------------------------
    async def ensure_loaded(self, db_path: Path) -> None:
        if self._ready:
            return
        async with self._lock:
            if not self._ready:
                await asyncio.to_thread(self._load_sync, db_path)

    # -------------------------------------------------------------------
    # Semantic search
    # -------------------------------------------------------------------
    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        if not self._ready or self._model is None or self._embeddings is None or self._metadata is None:
            raise RuntimeError("SemanticSearchEngine is not loaded yet.")

        query_vec: np.ndarray = self._model.encode([query], convert_to_numpy=True)[0]
        scores = _cosine_scores(query_vec, self._embeddings)
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [
            {**self._metadata[int(i)], "score": float(scores[int(i)])}
            for i in top_indices
        ]
