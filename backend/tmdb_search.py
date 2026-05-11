import json
import os
from typing import Any
from urllib import request as urllib_request
from urllib.parse import urlencode, quote as url_quote

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

# TV-specific genre mappings (TMDB uses different IDs for TV)
TV_GENRE_NAME_TO_ID: dict[str, int] = {
    "action": 10759,
    "adventure": 10759,
    "action & adventure": 10759,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 10765,
    "kids": 10762,
    "mystery": 9648,
    "reality": 10764,
    "romance": 10749,
    "science fiction": 10765,
    "sci-fi": 10765,
    "sci-fi & fantasy": 10765,
    "thriller": 9648,
    "war": 10768,
    "western": 37,
}

TV_GENRE_ID_TO_NAME: dict[int, str] = {
    10759: "Action & Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    10762: "Kids", 9648: "Mystery", 10764: "Reality",
    10749: "Romance", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
    10768: "War & Politics", 37: "Western",
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


def get_movies_by_actor(name: str, page: int = 1) -> list[dict[str, Any]]:
    """Find movies featuring a specific actor/director."""
    data = _tmdb_get("search/person", {"query": name, "page": 1, "language": "en-US"})
    if not data or not data.get("results"):
        return []
    person = data["results"][0]
    person_id = person["id"]
    credits = _tmdb_get(f"person/{person_id}/movie_credits", {"language": "en-US"})
    if not credits:
        return []
    cast = credits.get("cast", [])
    crew = credits.get("crew", [])
    directed = [m for m in crew if m.get("job") == "Director"]
    # exclude documentary appearances where person plays themselves
    filtered_cast = [
        m for m in cast
        if str(m.get("character", "")).lower() not in ("himself", "herself", "themselves", "")
        or m.get("vote_count", 0) >= 500
    ]
    movies = filtered_cast + directed
    # require minimum vote threshold to exclude obscure docs
    movies = [m for m in movies if m.get("vote_count", 0) >= 100]
    seen: set[int] = set()
    unique = []
    for m in sorted(movies, key=lambda x: x.get("vote_count", 0), reverse=True):
        if m["id"] not in seen:
            seen.add(m["id"])
            unique.append(m)
    start = (page - 1) * 20
    return [_format_movie(m) for m in unique[start: start + 20]]


def get_tv_by_actor(name: str, page: int = 1) -> list[dict[str, Any]]:
    """Find TV shows featuring a specific actor/director."""
    data = _tmdb_get("search/person", {"query": name, "page": 1, "language": "en-US"})
    if not data or not data.get("results"):
        return []
    person_id = data["results"][0]["id"]
    credits = _tmdb_get(f"person/{person_id}/tv_credits", {"language": "en-US"})
    if not credits:
        return []
    cast = credits.get("cast", [])
    crew = credits.get("crew", [])
    directed = [m for m in crew if m.get("job") == "Director"]
    filtered_cast = [
        m for m in cast
        if str(m.get("character", "")).lower() not in ("himself", "herself", "themselves", "")
        or m.get("vote_count", 0) >= 200
    ]
    shows = filtered_cast + directed
    shows = [m for m in shows if m.get("vote_count", 0) >= 50]
    seen: set[int] = set()
    unique = []
    for m in sorted(shows, key=lambda x: x.get("vote_count", 0), reverse=True):
        if m["id"] not in seen:
            seen.add(m["id"])
            unique.append(m)
    start = (page - 1) * 20
    return [_format_tv(m) for m in unique[start: start + 20]]


def get_movies_by_theme(theme: str, page: int = 1, limit: int = 20) -> list[dict[str, Any]]:
    """Find movies matching a specific theme or motif using TMDB keyword search."""
    kw_data = _tmdb_get("search/keyword", {"query": theme, "page": 1})
    keyword_ids: list[int] = []
    if kw_data:
        keyword_ids = [k["id"] for k in kw_data.get("results", [])[:5]]
    extra_pages = range(page, page + (2 if limit > 20 else 1))
    if keyword_ids:
        ids_str = "|".join(str(i) for i in keyword_ids)
        results: list[dict[str, Any]] = []
        for p in extra_pages:
            data = _tmdb_get("discover/movie", {
                "with_keywords": ids_str,
                "language": "en-US",
                "include_adult": "false",
                "sort_by": "popularity.desc",
                "vote_count.gte": "50",
                "page": p,
            })
            results.extend(data.get("results", []) if data else [])
        if results:
            return [_format_movie(m) for m in results[:limit]]
    # fallback: discover by text search sorted by popularity
    results = []
    for p in extra_pages:
        data = _tmdb_get("search/movie", {
            "query": theme,
            "page": p,
            "include_adult": "false",
            "language": "en-US",
        })
        results.extend(data.get("results", []) if data else [])
    results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return [_format_movie(m) for m in results[:limit]]


def get_tv_by_theme(theme: str, page: int = 1, limit: int = 20) -> list[dict[str, Any]]:
    """Find TV shows matching a specific theme or motif."""
    kw_data = _tmdb_get("search/keyword", {"query": theme, "page": 1})
    keyword_ids: list[int] = []
    if kw_data:
        keyword_ids = [k["id"] for k in kw_data.get("results", [])[:5]]
    extra_pages = range(page, page + (2 if limit > 20 else 1))
    if keyword_ids:
        ids_str = "|".join(str(i) for i in keyword_ids)
        results: list[dict[str, Any]] = []
        for p in extra_pages:
            data = _tmdb_get("discover/tv", {
                "with_keywords": ids_str,
                "language": "en-US",
                "include_adult": "false",
                "sort_by": "popularity.desc",
                "vote_count.gte": "30",
                "page": p,
            })
            results.extend(data.get("results", []) if data else [])
        if results:
            return [_format_tv(m) for m in results[:limit]]
    results = []
    for p in extra_pages:
        data = _tmdb_get("search/tv", {
            "query": theme,
            "page": p,
            "include_adult": "false",
            "language": "en-US",
        })
        results.extend(data.get("results", []) if data else [])
    results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return [_format_tv(m) for m in results[:limit]]


def fetch_movies_by_titles(titles: list[str]) -> list[dict[str, Any]]:
    """Search TMDB for each title in the list and return the best match per title."""
    results = []
    seen: set[int] = set()
    for title in titles:
        data = _tmdb_get("search/movie", {
            "query": title,
            "page": 1,
            "include_adult": "false",
            "language": "en-US",
        })
        if not data or not data.get("results"):
            continue
        movie = data["results"][0]
        if movie["id"] not in seen:
            seen.add(movie["id"])
            results.append(_format_movie(movie))
    return results


def fetch_tv_by_titles(titles: list[str]) -> list[dict[str, Any]]:
    """Search TMDB for each TV show title in the list and return the best match per title."""
    results = []
    seen: set[int] = set()
    for title in titles:
        data = _tmdb_get("search/tv", {
            "query": title,
            "page": 1,
            "include_adult": "false",
            "language": "en-US",
        })
        if not data or not data.get("results"):
            continue
        show = data["results"][0]
        if show["id"] not in seen:
            seen.add(show["id"])
            results.append(_format_tv(show))
    return results


def get_similar_movies(title: str, page: int = 1) -> list[dict[str, Any]]:
    """Find movies similar to a given title using TMDB recommendations."""
    data = _tmdb_get("search/movie", {"query": title, "page": 1, "include_adult": "false", "language": "en-US"})
    if not data or not data.get("results"):
        return []
    movie_id = data["results"][0]["id"]
    rec = _tmdb_get(f"movie/{movie_id}/recommendations", {"language": "en-US", "page": page})
    results = rec.get("results", []) if rec else []
    if not results:
        sim = _tmdb_get(f"movie/{movie_id}/similar", {"language": "en-US", "page": page})
        results = sim.get("results", []) if sim else []
    return [_format_movie(m) for m in results[:20]]


def get_similar_tv(title: str, page: int = 1) -> list[dict[str, Any]]:
    """Find TV shows similar to a given title using TMDB recommendations."""
    data = _tmdb_get("search/tv", {"query": title, "page": 1, "include_adult": "false", "language": "en-US"})
    if not data or not data.get("results"):
        return []
    show_id = data["results"][0]["id"]
    rec = _tmdb_get(f"tv/{show_id}/recommendations", {"language": "en-US", "page": page})
    results = rec.get("results", []) if rec else []
    if not results:
        sim = _tmdb_get(f"tv/{show_id}/similar", {"language": "en-US", "page": page})
        results = sim.get("results", []) if sim else []
    return [_format_tv(m) for m in results[:20]]


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


def _format_tv(m: dict[str, Any]) -> dict[str, Any]:
    genre_ids: list[int] = m.get("genre_ids", [])
    genres_str = " | ".join(TV_GENRE_ID_TO_NAME.get(gid, str(gid)) for gid in genre_ids)
    release = (m.get("first_air_date") or "")[:4] or None
    poster = f"{TMDB_IMAGE_BASE}{m['poster_path']}" if m.get("poster_path") else None
    return {
        "movieId": m.get("id", 0),
        "title": m.get("name", ""),
        "genres": genres_str,
        "description": m.get("overview") or None,
        "poster_url": poster,
        "release_date": release,
        "tmdb_rating": m.get("vote_average"),
        "score": None,
        "media_type": "tv",
    }


def search_tv(query: str, page: int = 1) -> list[dict[str, Any]]:
    """Full-text search via TMDB /search/tv."""
    data = _tmdb_get("search/tv", {
        "query": query,
        "page": page,
        "include_adult": "false",
        "language": "en-US",
    })
    if not data:
        return []
    return [_format_tv(m) for m in data.get("results", [])]


def discover_tv(params: dict[str, Any], page: int = 1) -> list[dict[str, Any]]:
    """Discover TV series using structured filters via TMDB /discover/tv."""
    q: dict[str, Any] = {
        "language": "en-US",
        "include_adult": "false",
        "page": page,
    }

    genre = str(params.get("genre", "")).strip().lower()
    if genre:
        genre_id = TV_GENRE_NAME_TO_ID.get(genre)
        if genre_id:
            q["with_genres"] = str(genre_id)

    if params.get("year"):
        q["first_air_date_year"] = str(params["year"])
    if params.get("year_gte"):
        q["first_air_date.gte"] = f"{params['year_gte']}-01-01"
    if params.get("year_lte"):
        q["first_air_date.lte"] = f"{params['year_lte']}-12-31"

    if params.get("min_rating"):
        q["vote_average.gte"] = str(params["min_rating"])
        q["vote_count.gte"] = "50"

    tv_sort_map = {
        "popular": "popularity.desc",
        "popularity": "popularity.desc",
        "rating": "vote_average.desc",
        "newest": "first_air_date.desc",
        "oldest": "first_air_date.asc",
        "revenue": "popularity.desc",  # no revenue for TV, fallback to popularity
    }
    sort = str(params.get("sort_by", "popular")).lower()
    q["sort_by"] = tv_sort_map.get(sort, "popularity.desc")

    data = _tmdb_get("discover/tv", q)
    if not data:
        return []
    return [_format_tv(m) for m in data.get("results", [])[:20]]


def get_tv_detail(tmdb_id: int) -> dict[str, Any] | None:
    """Fetch full TV series details from TMDB by TMDB TV ID."""
    data = _tmdb_get(f"tv/{tmdb_id}", {"language": "en-US"})
    if not data:
        return None
    genre_names = " | ".join(g["name"] for g in data.get("genres", []))
    poster = f"{TMDB_IMAGE_BASE}{data['poster_path']}" if data.get("poster_path") else None
    release = (data.get("first_air_date") or "")[:4] or None
    runtimes: list[int] = data.get("episode_run_time", [])
    runtime = runtimes[0] if runtimes else None
    ext_ids = _tmdb_get(f"tv/{tmdb_id}/external_ids", {}) or {}
    providers = get_watch_providers(tmdb_id, data.get("name", ""), media_type="tv")
    return {
        "movieId": data.get("id", 0),
        "title": data.get("name", ""),
        "genres": genre_names,
        "description": data.get("overview") or None,
        "plot": data.get("tagline") or None,
        "poster_url": poster,
        "tmdbId": str(data.get("id", "")),
        "imdbId": ext_ids.get("imdb_id"),
        "tmdb_rating": data.get("vote_average"),
        "release_date": release,
        "runtime": runtime,
        "watch_providers": providers,
        "media_type": "tv",
    }


JUSTWATCH_GQL = "https://apis.justwatch.com/graphql"

_JW_QUERY_MOVIE = """
query ($query: String!, $country: Country!, $language: Language!) {
  popularTitles(
    country: $country
    first: 10
    filter: { searchQuery: $query, objectTypes: [MOVIE] }
  ) {
    edges {
      node {
        ... on Movie {
          content(country: $country, language: $language) {
            externalIds { tmdbId }
          }
          offers(country: $country, platform: WEB) {
            standardWebURL
            monetizationType
            package { packageId clearName }
          }
        }
      }
    }
  }
}
"""

_JW_QUERY_TV = """
query ($query: String!, $country: Country!, $language: Language!) {
  popularTitles(
    country: $country
    first: 10
    filter: { searchQuery: $query, objectTypes: [SHOW] }
  ) {
    edges {
      node {
        ... on Show {
          content(country: $country, language: $language) {
            externalIds { tmdbId }
          }
          offers(country: $country, platform: WEB) {
            standardWebURL
            monetizationType
            package { packageId clearName }
          }
        }
      }
    }
  }
}
"""


def _justwatch_offers(tmdb_id: int, title: str, media_type: str = "movie") -> dict[int, str]:
    """Return {jw_package_id: direct_url} from JustWatch GraphQL, matched by TMDB ID."""
    if not title:
        return {}
    jw_query = _JW_QUERY_TV if media_type == "tv" else _JW_QUERY_MOVIE
    body = json.dumps({
        "query": jw_query,
        "variables": {"query": title, "country": "PL", "language": "pl"},
    }).encode()
    req = urllib_request.Request(
        JUSTWATCH_GQL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=8) as res:
            data = json.loads(res.read())
    except Exception:
        return {}

    tmdb_str = str(tmdb_id)
    edges = (data.get("data") or {}).get("popularTitles", {}).get("edges", [])
    for edge in edges:
        node = edge.get("node", {})
        ext = (node.get("content") or {}).get("externalIds") or {}
        if str(ext.get("tmdbId", "")) != tmdb_str:
            continue
        result: dict[int, str] = {}
        seen_pkg: set[int] = set()
        for offer in node.get("offers", []):
            pkg = offer.get("package") or {}
            pkg_id = pkg.get("packageId")
            url = offer.get("standardWebURL", "")
            if pkg_id and url and pkg_id not in seen_pkg:
                seen_pkg.add(pkg_id)
                result[pkg_id] = url
        return result
    return {}


def get_watch_providers(tmdb_id: int, title: str = "", media_type: str = "movie") -> list[dict]:
    """Fetch streaming providers with direct links. Uses TMDB for logos/names, JustWatch for URLs."""
    tmdb_path = f"{media_type}/{tmdb_id}/watch/providers"
    tmdb_data = _tmdb_get(tmdb_path, {})
    if not tmdb_data:
        return []
    results = tmdb_data.get("results", {})
    region_key = "PL" if "PL" in results else ("US" if "US" in results else None)
    if not region_key:
        return []
    region_data = results[region_key]
    tmdb_watch_path = "tv" if media_type == "tv" else "movie"
    fallback_url = f"https://www.themoviedb.org/{tmdb_watch_path}/{tmdb_id}/watch?locale={region_key}"

    # JustWatch package IDs match TMDB provider_id for most platforms
    jw_urls = _justwatch_offers(tmdb_id, title, media_type)

    providers: list[dict] = []
    seen: set[int] = set()
    for ptype in ("flatrate", "rent", "buy"):
        for p in region_data.get(ptype, []):
            pid = p.get("provider_id")
            if pid in seen:
                continue
            seen.add(pid)
            logo = f"https://image.tmdb.org/t/p/w45{p['logo_path']}" if p.get("logo_path") else None
            # JustWatch packageId == TMDB provider_id for the same platforms
            url = jw_urls.get(pid) or fallback_url
            providers.append({
                "provider_name": p.get("provider_name", ""),
                "logo_url": logo,
                "type": ptype,
                "url": url,
            })
    return providers


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
        "watch_providers": get_watch_providers(tmdb_id, data.get("title", "")),
    }
