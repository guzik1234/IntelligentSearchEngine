"""
Build (or refresh) the Qdrant movie index from TMDB.

Usage:
    python scripts/build_index.py              # fetch up to 50 000 movies
    python scripts/build_index.py --limit 10000
    python scripts/build_index.py --batch-size 1024   # larger batch for GPU

Requires:
    TMDB_API_KEY and QDRANT_URL in .env (or environment).
    pip install qdrant-client sentence-transformers

GPU acceleration:
    sentence-transformers auto-detects CUDA.
    For CUDA torch: pip install torch --index-url https://download.pytorch.org/whl/cu121
"""

import argparse
import json
import logging
import os
import time
from pathlib import Path
from urllib import request as urllib_request
from urllib.parse import urlencode

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
QDRANT_PATH = os.getenv("QDRANT_PATH", str(_PROJECT_ROOT / "data" / "qdrant"))
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()

COLLECTION = "movies"
MODEL_NAME = "all-MiniLM-L6-v2"

GENRE_ID_TO_NAME: dict[int, str] = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    53: "Thriller", 10752: "War", 37: "Western",
}

# Discovery strategies — tried in order until target is reached.
# Each strategy maps to TMDB /discover/movie query params.
STRATEGIES: list[dict] = [
    {"sort_by": "popularity.desc"},
    {"sort_by": "vote_count.desc", "vote_count.gte": "200"},
    {"sort_by": "revenue.desc", "vote_count.gte": "200"},
    {"sort_by": "vote_average.desc", "vote_count.gte": "500"},
] + [
    {"sort_by": "popularity.desc", "with_genres": str(gid)}
    for gid in GENRE_ID_TO_NAME
] + [
    {
        "sort_by": "popularity.desc",
        "primary_release_date.gte": f"{decade}-01-01",
        "primary_release_date.lte": f"{decade + 9}-12-31",
    }
    for decade in range(1950, 2020, 10)
]


# ── TMDB helpers ──────────────────────────────────────────────────────────────

def _tmdb_get(path: str, params: dict) -> dict | None:
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TMDB_API_KEY is not set")
    params = {**params, "api_key": api_key}
    url = f"{TMDB_BASE}/{path}?{urlencode(params)}"
    try:
        req = urllib_request.Request(url, headers={"Accept": "application/json"})
        with urllib_request.urlopen(req, timeout=12) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        log.debug("TMDB %s failed: %s", path, exc)
        return None


def _format_movie(m: dict) -> dict:
    genre_ids: list[int] = m.get("genre_ids", [])
    genres_str = " | ".join(
        GENRE_ID_TO_NAME[gid] for gid in genre_ids if gid in GENRE_ID_TO_NAME
    )
    return {
        "movieId": m["id"],
        "title": m.get("title", ""),
        "genres": genres_str,
        "description": (m.get("overview") or "").strip(),
        "poster_url": f"{TMDB_IMAGE_BASE}{m['poster_path']}" if m.get("poster_path") else None,
        "release_date": (m.get("release_date") or "")[:4] or None,
        "tmdb_rating": m.get("vote_average"),
        "score": None,
        "media_type": "movie",
    }


def fetch_tmdb_movies(target: int = 50_000) -> list[dict]:
    """
    Fetch up to `target` unique movies using multiple TMDB discover strategies.
    Rate-limited to ~20 req/s (safe for TMDB free tier).
    """
    seen: set[int] = set()
    movies: list[dict] = []

    for idx, strategy in enumerate(STRATEGIES):
        if len(movies) >= target:
            break
        label = strategy.get("sort_by", "") + (
            f" genre={strategy['with_genres']}" if "with_genres" in strategy else ""
        )
        log.info("Strategy %d/%d: %s | collected: %d", idx + 1, len(STRATEGIES), label, len(movies))

        for page in range(1, 501):
            if len(movies) >= target:
                break
            data = _tmdb_get("discover/movie", {
                "language": "en-US",
                "include_adult": "false",
                "page": page,
                **strategy,
            })
            if not data or not data.get("results"):
                break

            new_in_page = 0
            for m in data["results"]:
                if m.get("id") and m["id"] not in seen:
                    seen.add(m["id"])
                    movies.append(_format_movie(m))
                    new_in_page += 1

            # Stop paging this strategy early if we're getting no new movies
            if new_in_page == 0 and page > 5:
                break

            time.sleep(0.05)  # ~20 req/s — well within TMDB limits

    log.info("Fetched %d unique movies total", len(movies))
    return movies[:target]


# ── Embedding helpers ─────────────────────────────────────────────────────────

def _build_text(movie: dict) -> str:
    """Construct the text string that gets embedded for a movie."""
    parts = [movie.get("title", "")]
    if movie.get("release_date"):
        parts[0] += f" ({movie['release_date']})"
    if movie.get("genres"):
        parts.append(movie["genres"])
    if movie.get("description"):
        parts.append(movie["description"])
    return ". ".join(filter(None, parts))


# ── Qdrant helpers ────────────────────────────────────────────────────────────

def _ensure_collection(client) -> None:
    from qdrant_client.models import Distance, VectorParams
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        log.info("Created Qdrant collection '%s'", COLLECTION)
    else:
        log.info("Collection '%s' already exists — upserting", COLLECTION)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build Qdrant movie index from TMDB")
    parser.add_argument("--limit", type=int, default=50_000, help="Max movies to index")
    parser.add_argument("--batch-size", type=int, default=512, help="Embedding batch size (use 1024+ on GPU)")
    args = parser.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("Device: %s", device)
    if device == "cuda":
        log.info("GPU: %s", torch.cuda.get_device_name(0))

    # ── Load embedding model ──────────────────────────────────────────────────
    log.info("Loading %s on %s...", MODEL_NAME, device)
    model = SentenceTransformer(MODEL_NAME, device=device)

    # ── Fetch movies from TMDB ────────────────────────────────────────────────
    movies = fetch_tmdb_movies(args.limit)
    if not movies:
        log.error("No movies fetched — check TMDB_API_KEY")
        return

    # ── Generate embeddings ───────────────────────────────────────────────────
    texts = [_build_text(m) for m in movies]
    log.info("Generating embeddings for %d movies (batch=%d)...", len(texts), args.batch_size)

    all_vectors: list[np.ndarray] = []
    for i in range(0, len(texts), args.batch_size):
        batch = texts[i : i + args.batch_size]
        vecs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        all_vectors.append(vecs)
        if i % (args.batch_size * 20) == 0:
            log.info("  Embedded %d / %d", min(i + args.batch_size, len(texts)), len(texts))

    vectors = np.vstack(all_vectors)
    log.info("Embeddings shape: %s", vectors.shape)

    # ── Connect to Qdrant and upsert ──────────────────────────────────────────
    if QDRANT_URL:
        client = QdrantClient(url=QDRANT_URL, timeout=60)
        log.info("Qdrant: remote %s", QDRANT_URL)
    else:
        Path(QDRANT_PATH).mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=QDRANT_PATH)
        log.info("Qdrant: local path %s", QDRANT_PATH)
    _ensure_collection(client)

    upsert_batch = 256
    for i in range(0, len(movies), upsert_batch):
        chunk_movies = movies[i : i + upsert_batch]
        chunk_vecs = vectors[i : i + upsert_batch]
        points = [
            PointStruct(id=m["movieId"], vector=v.tolist(), payload=m)
            for m, v in zip(chunk_movies, chunk_vecs)
        ]
        client.upsert(collection_name=COLLECTION, points=points)
        if i % (upsert_batch * 10) == 0:
            log.info("  Upserted %d / %d", min(i + upsert_batch, len(movies)), len(movies))

    log.info("Done. %d movies indexed in Qdrant collection '%s'.", len(movies), COLLECTION)


if __name__ == "__main__":
    main()
