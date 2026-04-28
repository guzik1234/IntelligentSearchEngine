import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _fetch_from_tmdb(tmdb_id: str, api_key: str) -> dict[str, Any] | None:
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={api_key}&language=en-US"
    try:
        req = urllib_request.Request(url, headers={"Accept": "application/json"})
        with urllib_request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:
        return None


def get_movie_details(movie_id: int, db_path: Path) -> dict[str, Any] | None:
    """Return enriched movie details, fetching from TMDB on first access and caching in SQLite."""
    api_key = os.getenv("TMDB_API_KEY", "").strip()

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT m.movieId, m.title, m.genres, m.description, m.plot, m.poster_url,
                   l.tmdbId, l.imdbId
            FROM movies m
            LEFT JOIN links l ON m.movieId = l.movieId
            WHERE m.movieId = ?
            """,
            (movie_id,),
        ).fetchone()

        if not row:
            return None

        movie_id_db, title, genres, description, plot, poster_url, tmdb_id, imdb_id = row

        # Return cached data if description exists or if we can't fetch more
        if description or not api_key or not tmdb_id:
            return {
                "movieId": movie_id_db,
                "title": title,
                "genres": genres,
                "description": description,
                "plot": plot,
                "poster_url": poster_url,
                "tmdbId": tmdb_id,
                "imdbId": imdb_id,
            }

        # Fetch from TMDB and cache
        data = _fetch_from_tmdb(tmdb_id, api_key)
        if not data:
            return {
                "movieId": movie_id_db,
                "title": title,
                "genres": genres,
                "description": None,
                "plot": None,
                "poster_url": None,
                "tmdbId": tmdb_id,
                "imdbId": imdb_id,
            }

        overview: str | None = data.get("overview") or None
        tagline: str | None = data.get("tagline") or None
        poster: str | None = (
            f"{TMDB_IMAGE_BASE}{data['poster_path']}" if data.get("poster_path") else None
        )

        cur.execute(
            "UPDATE movies SET description = ?, plot = ?, poster_url = ? WHERE movieId = ?",
            (overview, tagline, poster, movie_id_db),
        )
        conn.commit()

        return {
            "movieId": movie_id_db,
            "title": title,
            "genres": genres,
            "description": overview,
            "plot": tagline,
            "poster_url": poster,
            "tmdbId": tmdb_id,
            "imdbId": imdb_id,
            "tmdb_rating": data.get("vote_average"),
            "release_date": data.get("release_date"),
            "runtime": data.get("runtime"),
        }


def get_posters_batch(movie_ids: list[int], db_path: Path) -> dict[int, dict[str, Any]]:
    """Return poster_url and description for multiple movies, fetching from TMDB as needed."""
    if not movie_ids:
        return {}

    api_key = os.getenv("TMDB_API_KEY", "").strip()
    placeholders = ",".join("?" * len(movie_ids))

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        rows = cur.execute(
            f"SELECT m.movieId, m.description, m.poster_url, l.tmdbId "
            f"FROM movies m LEFT JOIN links l ON m.movieId = l.movieId "
            f"WHERE m.movieId IN ({placeholders})",
            movie_ids,
        ).fetchall()

    result: dict[int, dict[str, Any]] = {}
    to_fetch: list[tuple[int, str]] = []

    for movie_id, description, poster_url, tmdb_id in rows:
        if description or poster_url:
            result[movie_id] = {"description": description, "poster_url": poster_url}
        elif api_key and tmdb_id:
            to_fetch.append((movie_id, tmdb_id))
        else:
            result[movie_id] = {"description": None, "poster_url": None}

    # Fetch missing from TMDB and cache
    if to_fetch:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            for movie_id, tmdb_id in to_fetch:
                data = _fetch_from_tmdb(tmdb_id, api_key)
                if data:
                    overview: str | None = data.get("overview") or None
                    poster: str | None = (
                        f"{TMDB_IMAGE_BASE}{data['poster_path']}" if data.get("poster_path") else None
                    )
                    cur.execute(
                        "UPDATE movies SET description = ?, poster_url = ? WHERE movieId = ?",
                        (overview, poster, movie_id),
                    )
                    result[movie_id] = {"description": overview, "poster_url": poster}
                else:
                    result[movie_id] = {"description": None, "poster_url": None}
            conn.commit()

    return result
