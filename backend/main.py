import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.sql_agent import SQLAgent
from backend import tmdb_search, qdrant_search

log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSET_FILES = {"app.js", "styles.css"}


# --- Request / Response models ---

class SearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    page: int = Field(default=1, ge=1, le=20)
    media_type: str = Field(default="movie", pattern="^(movie|tv)$")


class FilterRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    page: int = Field(default=1, ge=1, le=20)
    media_type: str = Field(default="movie", pattern="^(movie|tv)$")


class MovieCard(BaseModel):
    movieId: int
    title: str
    genres: str
    description: str | None = None
    poster_url: str | None = None
    release_date: str | None = None
    tmdb_rating: float | None = None
    score: float | None = None
    media_type: str = "movie"


class SearchResponse(BaseModel):
    movies: list[MovieCard]
    query_params: dict
    insight: str
    source: str
    page: int
    has_more: bool


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=20, ge=1, le=50)
    page: int = Field(default=1, ge=1, le=20)
    media_type: str = Field(default="movie", pattern="^(movie|tv)$")


class SemanticSearchResponse(BaseModel):
    results: list[MovieCard]
    query: str
    total: int
    page: int
    has_more: bool


class MovieDetailResponse(BaseModel):
    movieId: int
    title: str
    genres: str
    description: str | None = None
    plot: str | None = None
    poster_url: str | None = None
    tmdbId: str | None = None
    imdbId: str | None = None
    tmdb_rating: float | None = None
    release_date: str | None = None
    runtime: int | None = None
    watch_providers: list[dict] | None = None
    media_type: str = "movie"


# --- App setup ---

@asynccontextmanager
async def lifespan(_: FastAPI):
    asyncio.create_task(asyncio.to_thread(qdrant_search.preload_model))
    yield


app = FastAPI(title="IntelligentSearchEngine API", version="0.2.0", lifespan=lifespan)
sql_agent = SQLAgent()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


# --- Static files ---

@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "index.html")


@app.get("/{asset_name}")
def frontend_assets(asset_name: str) -> FileResponse:
    if asset_name not in ASSET_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(PROJECT_ROOT / asset_name)


# --- API endpoints ---

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/filter", response_model=SearchResponse)
async def filter_movies(request: FilterRequest) -> SearchResponse:
    """Direct TMDB discover — no LLM, params come straight from the UI."""
    try:
        if request.media_type == "tv":
            items = await asyncio.to_thread(tmdb_search.discover_tv, request.params, request.page)
        else:
            items = await asyncio.to_thread(tmdb_search.discover_movies, request.params, request.page)
    except Exception as exc:
        log.error("TMDB filter failed: %s", exc)
        raise HTTPException(status_code=503, detail="Movie database unavailable. Please try again later.")

    label = "series" if request.media_type == "tv" else "movies"
    insight = (
        f"Found {len(items)} {label} matching your filters."
        if items
        else f"No {label} found. Try adjusting the filters."
    )
    return SearchResponse(
        movies=[MovieCard(**m) for m in items],
        query_params=request.params,
        insight=insight,
        source="tmdb:discover",
        page=request.page,
        has_more=len(items) == 20,
    )


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    try:
        params, source = await sql_agent.generate_tmdb_params(request.question)
    except Exception as exc:
        log.warning("Groq param extraction failed: %s", exc)
        params, source = {"keyword": request.question}, "fallback"

    try:
        has_filters = any(k not in ("keyword", "sort_by") for k in params)
        if "similar_to" in params:
            similar_title = params["similar_to"]
            if request.media_type == "tv":
                movies = await asyncio.to_thread(tmdb_search.get_similar_tv, similar_title, request.page)
            else:
                movies = await asyncio.to_thread(tmdb_search.get_similar_movies, similar_title, request.page)
        elif "actor" in params:
            actor_name = params["actor"]
            if request.media_type == "tv":
                movies = await asyncio.to_thread(tmdb_search.get_tv_by_actor, actor_name, request.page)
            else:
                movies = await asyncio.to_thread(tmdb_search.get_movies_by_actor, actor_name, request.page)
        elif "theme" in params:
            theme = params["theme"]
            # Run TMDB keyword fetch AND Groq title suggestions in parallel
            if request.media_type == "tv":
                tmdb_task = asyncio.create_task(
                    asyncio.to_thread(tmdb_search.get_tv_by_theme, theme, request.page, 40)
                )
            else:
                tmdb_task = asyncio.create_task(
                    asyncio.to_thread(tmdb_search.get_movies_by_theme, theme, request.page, 40)
                )
            titles_task = asyncio.create_task(sql_agent.suggest_movies_for_plot(request.question, request.media_type))
            tmdb_candidates = await tmdb_task
            titles = await titles_task
            fetch_by_titles = tmdb_search.fetch_tv_by_titles if request.media_type == "tv" else tmdb_search.fetch_movies_by_titles
            title_candidates = (
                await asyncio.to_thread(fetch_by_titles, titles) if titles else []
            )
            # Merge deduplicated (title suggestions first — higher quality)
            seen: set[int] = set()
            candidates = []
            for m in title_candidates + tmdb_candidates:
                if m["movieId"] not in seen:
                    seen.add(m["movieId"])
                    candidates.append(m)
            movies = await sql_agent.rerank_with_groq(request.question, candidates)
            movies = movies[:20]
        elif "plot_description" in params:
            plot = params["plot_description"]
            # Run Groq title suggestions and keyword extraction in parallel
            keyword_task = asyncio.create_task(sql_agent.extract_search_keyword(plot))
            titles_task = asyncio.create_task(sql_agent.suggest_movies_for_plot(plot, request.media_type))
            keyword = await keyword_task
            titles = await titles_task
            # Fetch from TMDB by keyword
            if request.media_type == "tv":
                tmdb_candidates = await asyncio.to_thread(tmdb_search.get_tv_by_theme, keyword, request.page, 40)
            else:
                tmdb_candidates = await asyncio.to_thread(tmdb_search.get_movies_by_theme, keyword, request.page, 40)
            if not tmdb_candidates:
                search_fn = tmdb_search.search_tv if request.media_type == "tv" else tmdb_search.search_movies
                tmdb_candidates = await asyncio.to_thread(search_fn, keyword, request.page)
            # Fetch from TMDB by Groq-suggested titles
            fetch_by_titles = tmdb_search.fetch_tv_by_titles if request.media_type == "tv" else tmdb_search.fetch_movies_by_titles
            title_candidates = await asyncio.to_thread(fetch_by_titles, titles) if titles else []
            # Merge, deduplicate (title suggestions first — higher quality)
            seen: set[int] = set()
            candidates = []
            for m in title_candidates + tmdb_candidates:
                if m["movieId"] not in seen:
                    seen.add(m["movieId"])
                    candidates.append(m)
            movies = await sql_agent.rerank_with_groq(request.question, candidates)
            movies = movies[:20]
        elif request.media_type == "tv":
            if has_filters:
                movies = await asyncio.to_thread(tmdb_search.discover_tv, params, request.page)
                if not movies:
                    keyword = params.get("keyword") or request.question
                    movies = await asyncio.to_thread(tmdb_search.search_tv, keyword, request.page)
            else:
                keyword = params.get("keyword") or request.question
                movies = await asyncio.to_thread(tmdb_search.search_tv, keyword, request.page)
        else:
            if has_filters:
                movies = await asyncio.to_thread(tmdb_search.discover_movies, params, request.page)
                if not movies:
                    keyword = params.get("keyword") or request.question
                    movies = await asyncio.to_thread(tmdb_search.search_movies, keyword, request.page)
            else:
                keyword = params.get("keyword") or request.question
                movies = await asyncio.to_thread(tmdb_search.search_movies, keyword, request.page)
    except Exception as exc:
        log.error("TMDB search failed: %s", exc)
        raise HTTPException(status_code=503, detail="Movie database unavailable. Please try again later.")

    label = "series" if request.media_type == "tv" else "movies"
    insight = (
        f"Found {len(movies)} {label} matching your query."
        if movies
        else f"No {label} found. Try rephrasing your question."
    )

    return SearchResponse(
        movies=[MovieCard(**m) for m in movies],
        query_params=params,
        insight=insight,
        source=f"tmdb+{source}",
        page=request.page,
        has_more=len(movies) == 20,
    )


@app.post("/api/semantic-search", response_model=SemanticSearchResponse)
async def semantic_search(request: SemanticSearchRequest) -> SemanticSearchResponse:
    search_req = SearchRequest(question=request.query, page=request.page, media_type=request.media_type)

    if request.media_type == "tv":
        # Qdrant index covers movies only — TV falls back to TMDB routing
        search_resp = await search(search_req)
        results = search_resp.movies[: request.top_k]
        return SemanticSearchResponse(
            results=results,
            query=request.query,
            total=len(results),
            page=request.page,
            has_more=len(search_resp.movies) >= request.top_k,
        )

    # Hybrid: Qdrant similarity search + TMDB/Groq routing — run in parallel
    qdrant_task = asyncio.create_task(
        asyncio.to_thread(qdrant_search.search, request.query, 40)
    )
    tmdb_task = asyncio.create_task(search(search_req))

    qdrant_result, tmdb_result = await asyncio.gather(qdrant_task, tmdb_task, return_exceptions=True)

    qdrant_movies: list[dict] = qdrant_result if isinstance(qdrant_result, list) else []
    tmdb_movies: list[dict] = (
        [m.model_dump() for m in tmdb_result.movies]
        if isinstance(tmdb_result, SearchResponse)
        else []
    )

    # Merge — Qdrant first (semantic score already sorted), then TMDB supplements
    seen: set[int] = set()
    candidates: list[dict] = []
    for m in qdrant_movies + tmdb_movies:
        mid = m.get("movieId")
        if mid and mid not in seen:
            seen.add(mid)
            candidates.append(m)

    if candidates:
        candidates = await sql_agent.rerank_with_groq(request.query, candidates)

    final = candidates[: request.top_k]
    return SemanticSearchResponse(
        results=[MovieCard(**m) for m in final],
        query=request.query,
        total=len(final),
        page=request.page,
        has_more=len(candidates) > request.top_k,
    )


@app.get("/api/movies/{movie_id}", response_model=MovieDetailResponse)
async def movie_detail(movie_id: int) -> MovieDetailResponse:
    try:
        data = await asyncio.to_thread(tmdb_search.get_movie_detail, movie_id)
    except Exception as exc:
        log.error("TMDB movie detail failed for id=%s: %s", movie_id, exc)
        raise HTTPException(status_code=503, detail="Movie database unavailable. Please try again later.")
    if data is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return MovieDetailResponse(**data)


@app.get("/api/tv/{tv_id}", response_model=MovieDetailResponse)
async def tv_detail(tv_id: int) -> MovieDetailResponse:
    try:
        data = await asyncio.to_thread(tmdb_search.get_tv_detail, tv_id)
    except Exception as exc:
        log.error("TMDB TV detail failed for id=%s: %s", tv_id, exc)
        raise HTTPException(status_code=503, detail="Movie database unavailable. Please try again later.")
    if data is None:
        raise HTTPException(status_code=404, detail="TV series not found")
    return MovieDetailResponse(**data)
