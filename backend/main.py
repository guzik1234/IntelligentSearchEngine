import asyncio
import logging
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
from backend import tmdb_search

log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSET_FILES = {"app.js", "styles.css"}


# --- Request / Response models ---

class SearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    page: int = Field(default=1, ge=1, le=20)


class FilterRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    page: int = Field(default=1, ge=1, le=20)


class MovieCard(BaseModel):
    movieId: int
    title: str
    genres: str
    description: str | None = None
    poster_url: str | None = None
    release_date: str | None = None
    tmdb_rating: float | None = None
    score: float | None = None


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


# --- App setup ---

app = FastAPI(title="IntelligentSearchEngine API", version="0.2.0")
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
        movies = await asyncio.to_thread(tmdb_search.discover_movies, request.params, request.page)
    except Exception as exc:
        log.error("TMDB filter failed: %s", exc)
        raise HTTPException(status_code=503, detail="Movie database unavailable. Please try again later.")

    insight = (
        f"Found {len(movies)} movies matching your filters."
        if movies
        else "No movies found. Try adjusting the filters."
    )
    return SearchResponse(
        movies=[MovieCard(**m) for m in movies],
        query_params=request.params,
        insight=insight,
        source="tmdb:discover",
        page=request.page,
        has_more=len(movies) == 20,
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

    insight = (
        f"Found {len(movies)} movies matching your query."
        if movies
        else "No movies found. Try rephrasing your question."
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
    try:
        keyword = await sql_agent.extract_search_keyword(request.query)
    except Exception as exc:
        log.warning("Keyword extraction failed: %s", exc)
        keyword = " ".join(request.query.split()[:5])

    try:
        movies = await asyncio.to_thread(tmdb_search.search_movies, keyword, request.page)
        if not movies and " " in keyword:
            for word in keyword.split():
                if len(word) > 3:
                    movies = await asyncio.to_thread(tmdb_search.search_movies, word, request.page)
                    if movies:
                        break
    except Exception as exc:
        log.error("TMDB semantic search failed: %s", exc)
        raise HTTPException(status_code=503, detail="Movie database unavailable. Please try again later.")

    results = movies[: request.top_k]
    return SemanticSearchResponse(
        results=[MovieCard(**m) for m in results],
        query=request.query,
        total=len(results),
        page=request.page,
        has_more=len(movies) >= request.top_k,
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
