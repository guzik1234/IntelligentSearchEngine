import json
import os
from typing import Any
from urllib import request as urllib_request
from urllib.parse import urlencode

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

GENRE_NAME_TO_ID: dict[str, int] = {
    "action": 28,
    "adventure": 12,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "horror": 27,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "science fiction": 878,
    "sci-fi": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}

GENRE_ID_TO_NAME: dict[int, str] = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    53: "Thriller", 10752: "War", 37: "Western",
}

SORT_MAP: dict[str, str] = {
    "popular": "popularity.desc",
    "popularity": "popularity.desc",
    "rating": "vote_average.desc",
    "newest": "primary_release_date.desc",
    "oldest": "primary_release_date.asc",
    "revenue": "revenue.desc",
}


def _get_api_key() -> str:
    return os.getenv("TMDB_API_KEY", "").strip()


def _tmdb_get(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    api_key = _get_api_key()
    if not api_key:
        return None
    params["api_key"] = api_key
    url = f"{TMDB_BASE_URL}/{path}?{urlencode(params)}"
    try:
        req = urllib_request.Request(url, headers={"Accept": "application/json"})
        with urllib_request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:
        return None


def _format_movie(m: dict[str, Any]) -> dict[str, Any]:
    genre_ids: list[int] = m.get("genre_ids", [])
    genres_str = " | ".join(GENRE_ID_TO_NAME.get(gid, str(gid)) for gid in genre_ids)
    release = (m.get("release_date") or "")[:4] or None
    poster = f"{TMDB_IMAGE_BASE}{m['poster_path']}" if m.get("poster_path") else None
    return {
        "movieId": m.get("id", 0),
        "title": m.get("title", ""),
        "genres": genres_str,
        "description": m.get("overview") or None,
        "poster_url": poster,
        "release_date": release,
        "tmdb_rating": m.get("vote_average"),
        "score": None,
    }


def search_movies(query: str, page: int = 1) -> list[dict[str, Any]]:
    """Full-text search via TMDB /search/movie."""
    data = _tmdb_get("search/movie", {
        "query": query,
        "page": page,
        "include_adult": "false",
        "language": "en-US",
    })
    if not data:
        return []
    return [_format_movie(m) for m in data.get("results", [])]


def discover_movies(params: dict[str, Any], page: int = 1) -> list[dict[str, Any]]:
    """Discover movies using structured filters via TMDB /discover/movie."""
    q: dict[str, Any] = {
        "language": "en-US",
        "include_adult": "false",
        "page": page,
    }

    genre = str(params.get("genre", "")).strip().lower()
    if genre:
        genre_id = GENRE_NAME_TO_ID.get(genre)
        if genre_id:
            q["with_genres"] = str(genre_id)

    if params.get("year"):
        q["primary_release_year"] = str(params["year"])
    if params.get("year_gte"):
        q["primary_release_date.gte"] = f"{params['year_gte']}-01-01"
    if params.get("year_lte"):
        q["primary_release_date.lte"] = f"{params['year_lte']}-12-31"

    if params.get("min_rating"):
        q["vote_average.gte"] = str(params["min_rating"])
        q["vote_count.gte"] = "100"

    sort = str(params.get("sort_by", "popular")).lower()
    q["sort_by"] = SORT_MAP.get(sort, "popularity.desc")

    data = _tmdb_get("discover/movie", q)
    if not data:
        return []
    return [_format_movie(m) for m in data.get("results", [])[:20]]


def get_movie_detail(tmdb_id: int) -> dict[str, Any] | None:
    """Fetch full movie details from TMDB by TMDB movie ID."""
    data = _tmdb_get(f"movie/{tmdb_id}", {"language": "en-US"})
    if not data:
        return None
    genre_names = " | ".join(g["name"] for g in data.get("genres", []))
    poster = f"{TMDB_IMAGE_BASE}{data['poster_path']}" if data.get("poster_path") else None
    release = (data.get("release_date") or "")[:4] or None
    return {
        "movieId": data.get("id", 0),
        "title": data.get("title", ""),
        "genres": genre_names,
        "description": data.get("overview") or None,
        "plot": data.get("tagline") or None,
        "poster_url": poster,
        "tmdbId": str(data.get("id", "")),
        "imdbId": data.get("imdb_id"),
        "tmdb_rating": data.get("vote_average"),
        "release_date": release,
        "runtime": data.get("runtime"),
    }
